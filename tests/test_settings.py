import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import backend.database as db_module
import backend.config as config
from backend.database import Setting
from backend.main import app


AUTH_HEADERS = {"X-API-Key": config.SECRET_KEY, "X-Requested-By": "VibeListen"}


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    """Provide a fresh in-memory SQLite engine for settings tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="client", autouse=True)
def client_fixture(db_engine):
    """Override the main app database with our test in-memory DB."""
    original_db_engine = db_module.engine
    db_module.engine = db_engine

    # Initialize the test database tables
    SQLModel.metadata.create_all(db_engine)

    with TestClient(app) as client:
        yield client

    db_module.engine = original_db_engine


# --- Auth rejection tests ---

def test_api_rejects_missing_key(client):
    """Protected endpoints should return 401 without X-API-Key."""
    response = client.get("/api/settings")
    assert response.status_code == 401
    assert "Invalid or missing" in response.json()["detail"]


def test_api_rejects_wrong_key(client):
    """Protected endpoints should return 401 with wrong X-API-Key."""
    response = client.get("/api/settings", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_public_endpoints_no_auth_required(client):
    """Public endpoints should be accessible without X-API-Key."""
    response = client.get("/rss.xml")
    assert response.status_code in (200, 304)


# --- Settings CRUD tests ---

def test_get_settings_empty(client):
    """GET /api/settings should return empty object when no settings exist."""
    response = client.get("/api/settings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json() == {}


def test_update_and_get_setting(client):
    """POST /api/settings should create a setting, and GET should return it."""
    response = client.post(
        "/api/settings",
        data={"key": "tts_engine", "value": "piper", "section": "tts"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["key"] == "tts_engine"
    assert data["value"] == "piper"
    assert data["section"] == "tts"

    # Verify it can be retrieved
    response = client.get("/api/settings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    settings = response.json()
    assert settings["tts"]["tts_engine"] == "piper"


def test_update_existing_setting(client):
    """POST /api/settings should update an existing setting value."""
    client.post("/api/settings", data={"key": "theme", "value": "dark"}, headers=AUTH_HEADERS)
    client.post("/api/settings", data={"key": "theme", "value": "light"}, headers=AUTH_HEADERS)

    response = client.get("/api/settings", headers=AUTH_HEADERS)
    settings = response.json()
    assert settings["general"]["theme"] == "light"


def test_get_tts_engines(client):
    """GET /api/tts/engines should list all engines with availability status."""
    response = client.get("/api/tts/engines", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data
    assert "edge" in data["engines"]
    assert data["engines"]["edge"] is True


def test_get_voices_edge(client):
    """GET /api/tts/voices/edge should return Edge TTS voice list."""
    response = client.get("/api/tts/voices/edge", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0
    assert any(v["id"] == "en-US-GuyNeural" for v in data["voices"])


def test_get_voices_piper(client):
    """GET /api/tts/voices/piper should return Piper voice list."""
    response = client.get("/api/tts/voices/piper", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0


def test_get_voices_pocket(client):
    """GET /api/tts/voices/pocket should return Pocket voice list."""
    response = client.get("/api/tts/voices/pocket", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0
    assert any(v["id"] == "cloned" for v in data["voices"])


def test_get_voices_unknown_engine(client):
    """GET /api/tts/voices/nonsense should return 400."""
    response = client.get("/api/tts/voices/nonsense", headers=AUTH_HEADERS)
    assert response.status_code == 400


def test_upload_reference_audio(client, tmp_path):
    """POST /api/tts/reference should accept a valid WAV file upload."""
    import wave
    wav_file = tmp_path / "test_ref.wav"
    with wave.open(str(wav_file), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)

    wav_bytes = wav_file.read_bytes()
    with open(wav_file, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reference.wav" in data["path"]
    assert data["size"] == len(wav_bytes)


def test_upload_reference_audio_rejects_non_wav(client, tmp_path):
    """POST /api/tts/reference should reject non-WAV files."""
    mp3_file = tmp_path / "test.mp3"
    mp3_file.write_bytes(b"fake_mp3_data")

    with open(mp3_file, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f}, headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert "Only .wav files" in response.json()["detail"]


def test_upload_reference_audio_rejects_oversized(client, tmp_path):
    """POST /api/tts/reference should reject files exceeding the size limit."""
    from backend.main import MAX_REFERENCE_UPLOAD
    large_wav = tmp_path / "too_large.wav"
    # Write one byte past the limit
    large_wav.write_bytes(b"\x00" * (MAX_REFERENCE_UPLOAD + 1))

    with open(large_wav, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f}, headers=AUTH_HEADERS)

    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]


def test_upload_reference_audio_rejects_bad_header(client, tmp_path):
    """POST /api/tts/reference should reject .wav files with invalid RIFF header."""
    bad_wav = tmp_path / "fake.wav"
    # File has .wav extension but content doesn't start with RIFF
    bad_wav.write_bytes(b"\x00\x00\x00\x00" + b"\x00" * 100)

    with open(bad_wav, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f}, headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert "RIFF" in response.json()["detail"]


# --- Secret redaction tests ---

def test_get_settings_redacts_secrets(client):
    """GET /api/settings should redact secret values."""
    # Set a secret key via API
    client.post(
        "/api/settings",
        data={"key": "raindrop_token", "value": "my-real-token", "section": "raindrop"},
        headers=AUTH_HEADERS,
    )
    # Set a non-secret key
    client.post(
        "/api/settings",
        data={"key": "tts_engine", "value": "edge", "section": "tts"},
        headers=AUTH_HEADERS,
    )

    response = client.get("/api/settings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()

    # Secret key should be redacted
    assert data["raindrop"]["raindrop_token"] == "***REDACTED***"
    # Non-secret key should be plaintext
    assert data["tts"]["tts_engine"] == "edge"


def test_get_settings_redacts_all_secret_types(client):
    """All secret key patterns should be redacted in the response."""
    secrets = {
        "raindrop": {"raindrop_token": "abc"},
        "instapaper": {
            "instapaper_consumer_key": "key123",
            "instapaper_consumer_secret": "secret456",
            "instapaper_password": "pass789",
        },
    }
    for section, keys in secrets.items():
        for key, value in keys.items():
            client.post(
                "/api/settings",
                data={"key": key, "value": value, "section": section},
                headers=AUTH_HEADERS,
            )

    response = client.get("/api/settings", headers=AUTH_HEADERS)
    data = response.json()

    assert data["raindrop"]["raindrop_token"] == "***REDACTED***"
    assert data["instapaper"]["instapaper_consumer_key"] == "***REDACTED***"
    assert data["instapaper"]["instapaper_consumer_secret"] == "***REDACTED***"
    assert data["instapaper"]["instapaper_password"] == "***REDACTED***"


# --- Bookmark deletion path traversal test ---

def test_delete_bookmark_sanitizes_traversal_audio_filename(client, db_engine):
    """Deleting a bookmark with traversal in audio_filename should sanitize safely."""
    from datetime import datetime, timezone
    from backend.database import Bookmark
    from sqlmodel import Session as DBSession

    # Insert a bookmark with a traversal audio_filename
    with DBSession(db_engine) as session:
        bm = Bookmark(
            title="Traversal Test",
            url="https://example.com/traversal",
            domain="example.com",
            status="completed",
            audio_filename="../../etc/passwd",
            added_at=datetime.now(timezone.utc),
        )
        session.add(bm)
        session.commit()
        bm_id = bm.id

    # Deletion should succeed (filename is sanitized, no file outside AUDIO_DIR touched)
    response = client.delete(f"/api/bookmarks/{bm_id}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# --- Exception leak tests ---

def test_sync_failure_returns_user_facing_error(client):
    """Sync RuntimeError messages (invalid token, missing config) are user-facing."""
    from unittest.mock import patch
    with patch("backend.main.sync_bookmarks", side_effect=RuntimeError("Raindrop API token is Unauthorized")):
        response = client.post("/api/sync", headers=AUTH_HEADERS)
    assert response.status_code == 500
    assert "Unauthorized" in response.json()["detail"]


def test_sync_failure_hides_internal_error(client):
    """Non-RuntimeError exceptions return a generic message, hiding internals."""
    from unittest.mock import patch
    with patch("backend.main.sync_bookmarks", side_effect=KeyError("internal_key")):
        response = client.post("/api/sync", headers=AUTH_HEADERS)
    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]
    assert "internal_key" not in response.json()["detail"]


# --- Rate limiting tests ---

def test_rate_limit_sync_endpoint(client):
    """POST /api/sync should return 429 after exceeding rate limit."""
    from unittest.mock import patch

    with patch("backend.main.sync_bookmarks", return_value=0):
        # Exhaust the 5-per-minute limit
        for _ in range(5):
            response = client.post("/api/sync", headers=AUTH_HEADERS)
            assert response.status_code == 200

        # 6th request should be rate-limited
        response = client.post("/api/sync", headers=AUTH_HEADERS)
        assert response.status_code == 429


# --- CSRF tests ---

def test_post_rejects_missing_csrf_header(client):
    """POST /api/sync should be rejected without X-Requested-By header."""
    headers = {"X-API-Key": config.SECRET_KEY}
    response = client.post("/api/sync", headers=headers)
    assert response.status_code == 400
    assert "CSRF" in response.json()["detail"]


# --- Bulk settings tests ---

def test_bulk_update_settings(client):
    """POST /api/settings/bulk should update multiple settings in one request."""
    payload = {
        "tts": {"tts_engine": "piper", "tts_voice": "en_US-lessac-medium"},
        "general": {"max_rss_items": "25"},
    }
    response = client.post(
        "/api/settings/bulk",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify all settings were stored
    response = client.get("/api/settings", headers=AUTH_HEADERS)
    data = response.json()
    assert data["tts"]["tts_engine"] == "piper"
    assert data["tts"]["tts_voice"] == "en_US-lessac-medium"
    assert data["general"]["max_rss_items"] == "25"
