import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select, update

from backend.config import AUDIO_DIR
from backend.database import engine, init_db, Bookmark, get_setting
from backend.parser import extract_article_content
from backend.tts import generate_podcast_audio

logger = logging.getLogger("VibeListen.Worker")

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, scheduling graceful shutdown...")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


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
        if stalled:
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

            clean_text = extract_article_content(bookmark.url)
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

            filename = f"raindrop_{bookmark.raindrop_id}.mp3"
            output_path = AUDIO_DIR / filename

            stats = await generate_podcast_audio(
                text=bookmark.clean_text,
                title=bookmark.title,
                author=bookmark.author or "Unknown Author",
                output_path=str(output_path),
                voice=tts_voice,
                engine_name=tts_engine,
            )

            bookmark.audio_filename = filename
            bookmark.audio_filesize = stats["filesize"]
            bookmark.audio_duration = stats["duration"]
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
    logger.info("Worker starting up...")
    init_db()

    # Recovery: reset bookmarks left in limbo by a previous crash
    with Session(engine) as session:
        count = reset_stalled_bookmarks(session)
        if count:
            logger.info(f"Recovery complete: reset {count} stalled bookmark(s)")

    logger.info(f"Worker polling every {poll_interval}s. Press Ctrl+C to exit.")

    while not _shutdown_requested:
        try:
            with Session(engine) as session:
                bookmark = claim_next_bookmark(session)
                if bookmark:
                    await process_bookmark_pipeline_worker(bookmark.id)
                else:
                    await asyncio.sleep(poll_interval)
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
