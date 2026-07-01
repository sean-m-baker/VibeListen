import pytest
import hashlib
import shutil
from datetime import datetime, timezone
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import backend.database as db_module
from backend.database import Bookmark, Setting
from backend.main import app
from backend.config import AUDIO_DIR, AUDIO_CACHE_DIR


shutil_which = shutil.which


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="client", autouse=True)
def client_fixture(db_engine):
    original_db_engine = db_module.engine
    db_module.engine = db_engine

    SQLModel.metadata.create_all(db_engine)

    with TestClient(app) as client:
        yield client

    db_module.engine = original_db_engine


def _seed_bookmarks(db_engine, count: int, day_offset: int = 0):
    """Insert test bookmarks with completed status."""
    from sqlmodel import Session as DBSession
    with DBSession(db_engine) as session:
        for i in range(count):
            bm = Bookmark(
                title=f"Test Article {i}",
                url=f"https://example.com/{i}",
                domain="example.com",
                status="completed",
                audio_filename=f"test_{i}.wav",
                audio_duration=120.0 + i,
                audio_filesize=1000000 + i,
                clean_text=f"Summary of article {i}." * 10,
                added_at=datetime(2026, 1, 1 + day_offset, tzinfo=timezone.utc),
            )
            session.add(bm)
        session.commit()


def _set_setting(db_engine, key, value, section="general"):
    """Helper to insert a setting directly into the test DB."""
    from sqlmodel import Session as DBSession
    with DBSession(db_engine) as session:
        session.add(Setting(section=section, key=key, value=value))
        session.commit()


def test_rss_feed_returns_xml(client, db_engine):
    """GET /rss.xml should return valid XML with completed bookmarks."""
    _seed_bookmarks(db_engine, 3)
    response = client.get("/rss.xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert b"Test Article 0" in response.content
    assert b"Test Article 1" in response.content
    assert b"Test Article 2" in response.content
    assert b"<rss version=\"2.0\"" in response.content


def test_rss_feed_respects_max_items(client, db_engine):
    """RSS feed should respect the max_rss_items setting."""
    _seed_bookmarks(db_engine, 10)
    _set_setting(db_engine, "max_rss_items", "3", section="general")

    response = client.get("/rss.xml")
    assert response.status_code == 200
    assert response.content.count(b"<item>") == 3


def test_rss_feed_defaults_to_100_items(client, db_engine):
    """Without a max_rss_items setting, feed defaults to 100 items."""
    _seed_bookmarks(db_engine, 50)
    response = client.get("/rss.xml")
    assert response.status_code == 200
    assert response.content.count(b"<item>") == 50


def test_rss_feed_empty_when_no_completed(client, db_engine):
    """RSS feed should be valid XML with no items when no completed bookmarks exist."""
    response = client.get("/rss.xml")
    assert response.status_code == 200
    assert b"<item>" not in response.content
    assert b"<channel>" in response.content


def test_rss_feed_excludes_non_completed(client, db_engine):
    """Only bookmarks with status 'completed' should appear in the RSS feed."""
    from sqlmodel import Session as DBSession
    with DBSession(db_engine) as session:
        bm = Bookmark(
            title="Pending Article",
            url="https://example.com/pending",
            domain="example.com",
            status="pending",
            added_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add(bm)
        session.commit()

    response = client.get("/rss.xml")
    assert response.status_code == 200
    assert b"Pending Article" not in response.content


def test_rss_feed_uses_transcoded_audio_for_wav(client, db_engine):
    """WAV files should get MP3 enclosure URLs pointing to /rss-audio/."""
    _seed_bookmarks(db_engine, 1)
    response = client.get("/rss.xml")
    assert response.status_code == 200
    body = response.content.decode()
    assert "/rss-audio/test_0.mp3" in body
    assert "audio/mpeg" in body


def test_rss_feed_direct_audio_for_mp3(client, db_engine):
    """Native MP3 files should keep /audio/ enclosure URLs."""
    from sqlmodel import Session as DBSession
    with DBSession(db_engine) as session:
        bm = Bookmark(
            title="MP3 Article",
            url="https://example.com/mp3",
            domain="example.com",
            status="completed",
            audio_filename="track.mp3",
            audio_duration=60.0,
            audio_filesize=500000,
            added_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add(bm)
        session.commit()

    response = client.get("/rss.xml")
    assert response.status_code == 200
    body = response.content.decode()
    assert "/audio/track.mp3" in body
    assert "/rss-audio/" not in body


def test_rss_feed_etag_matches(client, db_engine):
    """RSS feed should return 304 when If-None-Match matches."""
    _seed_bookmarks(db_engine, 1)
    first = client.get("/rss.xml")
    etag = first.headers.get("etag")
    assert etag is not None

    second = client.get("/rss.xml", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""


def test_rss_feed_etag_changes_on_new_content(client, db_engine):
    """ETag should change after adding a new completed bookmark."""
    _seed_bookmarks(db_engine, 1, day_offset=0)
    first = client.get("/rss.xml")
    etag1 = first.headers.get("etag")

    _seed_bookmarks(db_engine, 1, day_offset=1)
    second = client.get("/rss.xml")
    etag2 = second.headers.get("etag")

    assert etag1 != etag2


def test_rss_feed_includes_wav_filesize_estimate(client, db_engine):
    """RSS enclosure length for WAV files should include estimated MP3 size."""
    _seed_bookmarks(db_engine, 1)
    response = client.get("/rss.xml")
    body = response.content.decode()
    # duration = 120.0, bitrate = 64 kbps -> (64000/8) * 120 = 960000 bytes
    assert 'length="960000"' in body


@pytest.mark.skipif(
    not shutil_which("ffmpeg"),
    reason="ffmpeg not available on this system"
)
def test_rss_audio_transcodes_wav_to_mp3(client, db_engine, tmp_path):
    """GET /rss-audio/{file}.mp3 should transcode WAV to MP3 on first request."""
    import shutil
    import wave

    # Create a test WAV file
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = AUDIO_DIR / "test_audio.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)  # 1 second of silence

    # Set audio_bitrate
    _set_setting(db_engine, "audio_bitrate", "64", section="tts")

    response = client.get("/rss-audio/test_audio.mp3")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 0

    # Cleanup
    wav_path.unlink(missing_ok=True)
    mp3_path = AUDIO_CACHE_DIR / "test_audio.mp3"
    mp3_path.unlink(missing_ok=True)


def test_rss_audio_rejects_non_mp3(client):
    """GET /rss-audio/{file} should reject non-MP3 requests."""
    response = client.get("/rss-audio/test.wav")
    assert response.status_code == 400


def test_rss_audio_rejects_traversal(client):
    """GET /rss-audio/ should reject path traversal sequences."""
    # Encoded traversal (not normalized by HTTP client)
    response = client.get("/rss-audio/..%2fetc%2fpasswd.mp3")
    assert response.status_code == 400

    # Direct traversal in filename
    response = client.get("/rss-audio/..%5c..%5cwindows%5csystem32.mp3")
    assert response.status_code == 400


def test_rss_audio_returns_404_for_missing_file(client):
    """GET /rss-audio/{file}.mp3 should return 404 if source WAV doesn't exist."""
    response = client.get("/rss-audio/nonexistent.mp3")
    assert response.status_code == 404



