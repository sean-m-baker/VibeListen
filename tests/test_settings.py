import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import backend.database as db_module
from backend.database import Setting
from backend.main import app


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


def test_get_settings_empty(client):
    """GET /api/settings should return empty object when no settings exist."""
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {}


def test_update_and_get_setting(client):
    """POST /api/settings should create a setting, and GET should return it."""
    response = client.post(
        "/api/settings",
        data={"key": "tts_engine", "value": "piper", "section": "tts"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["key"] == "tts_engine"
    assert data["value"] == "piper"
    assert data["section"] == "tts"

    # Verify it can be retrieved
    response = client.get("/api/settings")
    assert response.status_code == 200
    settings = response.json()
    assert settings["tts"]["tts_engine"] == "piper"


def test_update_existing_setting(client):
    """POST /api/settings should update an existing setting value."""
    client.post("/api/settings", data={"key": "theme", "value": "dark"})
    client.post("/api/settings", data={"key": "theme", "value": "light"})

    response = client.get("/api/settings")
    settings = response.json()
    assert settings["general"]["theme"] == "light"


def test_get_tts_engines(client):
    """GET /api/tts/engines should list all engines with availability status."""
    response = client.get("/api/tts/engines")
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data
    assert "edge" in data["engines"]
    assert data["engines"]["edge"] is True


def test_get_voices_edge(client):
    """GET /api/tts/voices/edge should return Edge TTS voice list."""
    response = client.get("/api/tts/voices/edge")
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0
    assert any(v["id"] == "en-US-GuyNeural" for v in data["voices"])


def test_get_voices_piper(client):
    """GET /api/tts/voices/piper should return Piper voice list."""
    response = client.get("/api/tts/voices/piper")
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0


def test_get_voices_pocket(client):
    """GET /api/tts/voices/pocket should return Pocket voice list."""
    response = client.get("/api/tts/voices/pocket")
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0
    assert any(v["id"] == "cloned" for v in data["voices"])


def test_get_voices_unknown_engine(client):
    """GET /api/tts/voices/nonsense should return 400."""
    response = client.get("/api/tts/voices/nonsense")
    assert response.status_code == 400


def test_upload_reference_audio(client, tmp_path):
    """POST /api/tts/reference should accept a WAV file upload."""
    wav_file = tmp_path / "test_ref.wav"
    wav_file.write_bytes(b"fake_wav_data")

    with open(wav_file, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reference.wav" in data["path"]
    assert data["size"] == len(b"fake_wav_data")


def test_upload_reference_audio_rejects_non_wav(client, tmp_path):
    """POST /api/tts/reference should reject non-WAV files."""
    mp3_file = tmp_path / "test.mp3"
    mp3_file.write_bytes(b"fake_mp3_data")

    with open(mp3_file, "rb") as f:
        response = client.post("/api/tts/reference", files={"file": f})

    assert response.status_code == 400
    assert "Only .wav files" in response.json()["detail"]
