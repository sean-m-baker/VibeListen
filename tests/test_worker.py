import pytest
from sqlmodel import Session, SQLModel, create_engine
from unittest.mock import patch, AsyncMock
from sqlalchemy.pool import StaticPool

import backend.database as db_module
from backend.database import Bookmark


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    """Provide a fresh in-memory SQLite engine using StaticPool for shared connection."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="worker")
def worker_fixture(db_engine):
    """
    Import backend.worker AFTER monkey-patching the database engine
    so the worker binds to our test in-memory DB instead of the file DB.
    """
    original_db_engine = db_module.engine
    db_module.engine = db_engine

    import backend.worker as worker_module
    original_worker_engine = getattr(worker_module, "engine", None)
    worker_module.engine = db_engine

    yield worker_module

    # Restore
    db_module.engine = original_db_engine
    if original_worker_engine is not None:
        worker_module.engine = original_worker_engine


def test_reset_stalled_bookmarks(worker, db_engine):
    with Session(db_engine) as session:
        bm1 = Bookmark(raindrop_id=1, title="Proc", url="http://x.com", domain="x.com", status="processing")
        bm2 = Bookmark(raindrop_id=2, title="Synth", url="http://x.com", domain="x.com", status="synthesizing")
        bm3 = Bookmark(raindrop_id=3, title="Done", url="http://x.com", domain="x.com", status="completed")
        bm4 = Bookmark(raindrop_id=4, title="ParseFail", url="http://x.com", domain="x.com", status="parsing_failed")
        bm5 = Bookmark(raindrop_id=5, title="Parsing", url="http://x.com", domain="x.com", status="parsing")
        session.add_all([bm1, bm2, bm3, bm4, bm5])
        session.commit()

        count = worker.reset_stalled_bookmarks(session)
        assert count == 3  # processing, synthesizing, parsing

        assert session.get(Bookmark, bm1.id).status == "queued"
        assert session.get(Bookmark, bm2.id).status == "queued"
        assert session.get(Bookmark, bm5.id).status == "queued"
        assert session.get(Bookmark, bm3.id).status == "completed"
        assert session.get(Bookmark, bm4.id).status == "parsing_failed"


def test_claim_next_bookmark_success(worker, db_engine):
    with Session(db_engine) as session:
        bm = Bookmark(raindrop_id=1, title="Test", url="http://x.com", domain="x.com", status="queued")
        session.add(bm)
        session.commit()

        claimed = worker.claim_next_bookmark(session)
        assert claimed is not None
        assert claimed.id == bm.id
        assert claimed.status == "processing"

        refreshed = session.get(Bookmark, bm.id)
        assert refreshed.status == "processing"


def test_claim_next_bookmark_empty(worker, db_engine):
    with Session(db_engine) as session:
        claimed = worker.claim_next_bookmark(session)
        assert claimed is None


def test_claim_next_bookmark_race_simulation(worker, db_engine):
    """
    After a bookmark is claimed, a second claim attempt on the same
    committed session should find no queued bookmarks left.
    """
    with Session(db_engine) as session:
        bm = Bookmark(raindrop_id=1, title="Test", url="http://x.com", domain="x.com", status="queued")
        session.add(bm)
        session.commit()

        claimed1 = worker.claim_next_bookmark(session)
        assert claimed1 is not None

        claimed2 = worker.claim_next_bookmark(session)
        assert claimed2 is None


@pytest.mark.asyncio
async def test_worker_pipeline_success(worker, db_engine):
    with Session(db_engine) as session:
        bm = Bookmark(raindrop_id=1, title="Test", url="http://x.com", domain="x.com", status="queued")
        session.add(bm)
        session.commit()
        bm_id = bm.id

    with patch("backend.worker.extract_article_content", return_value="Clean text"):
        with patch("backend.worker.generate_podcast_audio", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = {"filesize": 1234, "duration": 60.0}

            await worker.process_bookmark_pipeline_worker(bm_id)

    with Session(db_engine) as session:
        refreshed = session.get(Bookmark, bm_id)
        assert refreshed.status == "completed"
        assert refreshed.audio_filename == "raindrop_1.mp3"
        assert refreshed.audio_filesize == 1234
        assert refreshed.audio_duration == 60.0
        assert refreshed.clean_text == "Clean text"


@pytest.mark.asyncio
async def test_worker_pipeline_parsing_failure(worker, db_engine):
    with Session(db_engine) as session:
        bm = Bookmark(raindrop_id=1, title="Test", url="http://x.com", domain="x.com", status="queued")
        session.add(bm)
        session.commit()
        bm_id = bm.id

    with patch("backend.worker.extract_article_content", side_effect=Exception("Network down")):
        await worker.process_bookmark_pipeline_worker(bm_id)

    with Session(db_engine) as session:
        refreshed = session.get(Bookmark, bm_id)
        assert refreshed.status == "parsing_failed"


@pytest.mark.asyncio
async def test_worker_pipeline_synthesis_failure(worker, db_engine):
    with Session(db_engine) as session:
        bm = Bookmark(raindrop_id=1, title="Test", url="http://x.com", domain="x.com", status="queued")
        session.add(bm)
        session.commit()
        bm_id = bm.id

    with patch("backend.worker.extract_article_content", return_value="Clean text"):
        with patch("backend.worker.generate_podcast_audio", side_effect=Exception("TTS crash")):
            await worker.process_bookmark_pipeline_worker(bm_id)

    with Session(db_engine) as session:
        refreshed = session.get(Bookmark, bm_id)
        assert refreshed.status == "failed"


@pytest.mark.asyncio
async def test_worker_pipeline_missing_bookmark(worker, db_engine):
    """Processing a non-existent bookmark ID should be a no-op, not a crash."""
    await worker.process_bookmark_pipeline_worker(99999)
