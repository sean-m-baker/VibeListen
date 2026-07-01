import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select, update

from backend.auth import sanitize_filename
from backend.config import AUDIO_DIR, AUDIO_CACHE_DIR
from backend.database import engine, init_db, Bookmark, get_setting
from backend.parser import extract_article_content
from backend.tts import generate_podcast_audio

logger = logging.getLogger("VibeListen.Worker")

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, scheduling graceful shutdown...")
    _shutdown_requested = True


def reset_stalled_bookmarks(session: Session) -> int:
    """
    On startup, reset any bookmarks stuck in active processing states
    (processing, parsing, synthesizing) back to 'queued' so they can
    be retried by a healthy worker.
    """
    reset_count = 0
    for status in ["processing", "parsing", "synthesizing"]:
        statement = select(Bookmark).where(Bookmark.status == status)
        stalled = session.exec(statement).all()
        for bookmark in stalled:
            logger.warning(
                f"Resetting stalled bookmark {bookmark.id} from '{status}' to 'queued'"
            )
            bookmark.status = "queued"
            session.add(bookmark)
            reset_count += 1
    if reset_count:
        session.commit()
    return reset_count


def claim_next_bookmark(session: Session) -> Optional[Bookmark]:
    """
    Atomically claim the next queued bookmark by performing an UPDATE-WHERE.
    This SQL-level guard ensures that even with multiple concurrent worker
    processes, only one can successfully claim a given bookmark.
    """
    try:
        # 1. Identify the oldest queued candidate
        statement = (
            select(Bookmark)
            .where(Bookmark.status == "queued")
            .order_by(Bookmark.added_at.asc())
        )
        candidate = session.exec(statement).first()
        if not candidate:
            return None

        # 2. Atomic update: only succeed if still queued
        stmt = (
            update(Bookmark)
            .where(Bookmark.id == candidate.id, Bookmark.status == "queued")
            .values(status="processing")
        )
        result = session.exec(stmt)
        session.commit()

        if result.rowcount == 1:
            session.refresh(candidate)
            return candidate
        return None
    except Exception as e:
        logger.error(f"Failed to claim next bookmark: {e}")
        session.rollback()
        return None


async def process_bookmark_pipeline_worker(bookmark_id: int) -> None:
    """
    Standalone pipeline worker. Opens its own DB session, runs parsing +
    TTS synthesis, and updates the bookmark status to completed/failed.
    """
    with Session(engine) as session:
        bookmark = session.get(Bookmark, bookmark_id)
        if not bookmark:
            logger.error(f"Worker: Bookmark {bookmark_id} not found.")
            return

        logger.info(
            f"Worker processing bookmark {bookmark_id}: '{bookmark.title}'"
        )

        # Step 1: Parse content
        try:
            bookmark.status = "parsing"
            session.add(bookmark)
            session.commit()

            clean_text = await asyncio.to_thread(extract_article_content, bookmark.url)
            bookmark.clean_text = clean_text
            bookmark.status = "synthesizing"
            session.add(bookmark)
            session.commit()
        except Exception:
            logger.exception(f"Worker: Parsing failed for bookmark {bookmark_id}")
            bookmark.status = "parsing_failed"
            session.add(bookmark)
            session.commit()
            return

        # Step 2: Speech synthesis
        try:
            # Read TTS settings from database (with env fallbacks)
            tts_engine = get_setting(
                session, "tts_engine", default=os.getenv("TTS_ENGINE", "edge"), section="tts"
            )
            tts_voice = get_setting(
                session, "tts_voice", default=os.getenv("DEFAULT_VOICE", "en-US-GuyNeural"), section="tts"
            )

            if bookmark.raindrop_id:
                stem = sanitize_filename(f"raindrop_{bookmark.raindrop_id}")
            elif bookmark.instapaper_id:
                stem = sanitize_filename(f"instapaper_{bookmark.instapaper_id}")
            else:
                stem = sanitize_filename(f"bookmark_{bookmark.id}")
            output_path = AUDIO_DIR / f"{stem}.mp3"

            stats = await generate_podcast_audio(
                text=bookmark.clean_text,
                title=bookmark.title,
                author=bookmark.author or "Unknown Author",
                output_path=str(output_path),
                voice=tts_voice,
                engine_name=tts_engine,
            )

            actual_path = Path(stats["output_path"])
            bookmark.audio_filename = actual_path.name
            bookmark.audio_filesize = stats["filesize"]
            bookmark.audio_duration = stats["duration"]

            # Transcode WAV to MP3 in the background so the HTTP endpoint never
            # needs to spawn ffmpeg on-demand (prevents transcoding DoS).
            if actual_path.suffix == ".wav":
                mp3_name = actual_path.stem + ".mp3"
                mp3_path = AUDIO_CACHE_DIR / mp3_name
                mp3_path.parent.mkdir(parents=True, exist_ok=True)
                bitrate = get_setting(session, "audio_bitrate", "64", section="tts")
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(actual_path),
                    "-codec:a", "libmp3lame",
                    "-b:a", f"{bitrate}k",
                    "-ar", "24000",
                    "-ac", "1",
                    str(mp3_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()
                if process.returncode != 0:
                    logger.error("ffmpeg transcoding failed for %s: %s",
                                 actual_path, stderr.decode(errors="replace"))

            bookmark.status = "completed"
            bookmark.generated_at = datetime.now(timezone.utc)
            session.add(bookmark)
            session.commit()
            logger.info(f"Worker: Completed bookmark {bookmark_id} (engine={tts_engine}, voice={tts_voice})")
        except Exception:
            logger.exception(f"Worker: Synthesis failed for bookmark {bookmark_id}")
            bookmark.status = "failed"
            session.add(bookmark)
            session.commit()


async def run_worker(poll_interval: float = 2.0) -> None:
    """
    Main async poll loop. Claims queued bookmarks and processes them
    until graceful shutdown is requested.
    """
    # Register signal handlers here (not at module level) to avoid installing
    # them on import — e.g. when imported from tests or the FastAPI process
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Worker starting up...")
    init_db()

    # Recovery: reset bookmarks left in limbo by a previous crash
    with Session(engine) as session:
        count = reset_stalled_bookmarks(session)
        if count:
            logger.info(f"Recovery complete: reset {count} stalled bookmark(s)")

    logger.info(f"Worker polling every {poll_interval}s. Press Ctrl+C to exit.")

    consecutive_idle = 0
    while not _shutdown_requested:
        try:
            with Session(engine) as session:
                bookmark = claim_next_bookmark(session)
                if bookmark:
                    consecutive_idle = 0
                    await process_bookmark_pipeline_worker(bookmark.id)
                else:
                    consecutive_idle += 1
                    sleep_time = min(poll_interval * (1.5 ** min(consecutive_idle, 5)), 30.0)
                    await asyncio.sleep(sleep_time)
        except Exception:
            logger.exception("Worker: Unexpected error in main loop")
            await asyncio.sleep(poll_interval)

    logger.info("Worker shutdown gracefully.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    asyncio.run(run_worker())
