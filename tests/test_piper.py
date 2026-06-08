import os
import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

from backend.utils.downloader import ensure_piper_voice, download_file


def test_download_file_success(tmp_path):
    mock_content = b"fake onnx model bytes"
    dest = tmp_path / "model.onnx"

    with patch("backend.utils.downloader.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(mock_content))}
        mock_response.iter_content.return_value = [mock_content]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = download_file("http://example.com/model.onnx", dest)
        assert result is True
        assert dest.read_bytes() == mock_content


def test_download_file_failure_cleanup(tmp_path):
    dest = tmp_path / "model.onnx"

    with patch("backend.utils.downloader.requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Network error")

        result = download_file("http://example.com/model.onnx", dest)
        assert result is False
        assert not dest.exists()


def test_download_file_incomplete(tmp_path):
    mock_content = b"partial"
    dest = tmp_path / "model.onnx"

    with patch("backend.utils.downloader.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}  # Expect 100 bytes
        mock_response.iter_content.return_value = [mock_content]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = download_file("http://example.com/model.onnx", dest)
        assert result is False
        assert not dest.exists()


def test_ensure_piper_voice_already_exists(tmp_path):
    models_dir = tmp_path / "models"
    voice_dir = models_dir / "piper"
    voice_dir.mkdir(parents=True)
    (voice_dir / "test_voice.onnx").write_text("fake model")
    (voice_dir / "test_voice.onnx.json").write_text("fake config")

    result = ensure_piper_voice("test_voice", models_dir)
    assert result is not None
    assert result.name == "test_voice.onnx"


def test_ensure_piper_voice_downloads_missing(tmp_path):
    models_dir = tmp_path / "models"
    voice_dir = models_dir / "piper"
    voice_dir.mkdir(parents=True)

    def fake_download(url: str, dest: Path) -> bool:
        # Simulate successful download by creating the file
        dest.write_text("fake_content")
        return True

    with patch("backend.utils.downloader.download_file", side_effect=fake_download):
        result = ensure_piper_voice("test_voice", models_dir)
        assert result is not None
        assert result.name == "test_voice.onnx"


def test_ensure_piper_voice_download_failure(tmp_path):
    models_dir = tmp_path / "models"

    with patch("backend.utils.downloader.download_file") as mock_download:
        mock_download.return_value = False

        result = ensure_piper_voice("test_voice", models_dir)
        assert result is None


@pytest.fixture
def mock_piper_voice():
    """Creates a mock PiperVoice class and its instances."""
    with patch("backend.tts_engines.piper_engine.PiperVoice") as MockVoice:
        mock_instance = MagicMock()

        def fake_synthesize_wav(text, wav_file, syn_config=None, set_wav_format=True, **kwargs):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 22050)  # 1 second of silence
            return None

        mock_instance.synthesize_wav.side_effect = fake_synthesize_wav
        MockVoice.load.return_value = mock_instance
        yield MockVoice, mock_instance


def test_piper_engine_missing_dependency():
    with patch("backend.tts_engines.piper_engine.PiperVoice", None):
        from backend.tts_engines.piper_engine import PiperEngine
        with pytest.raises(RuntimeError, match="Piper TTS is not installed"):
            PiperEngine()


@pytest.mark.asyncio
async def test_piper_engine_synthesize_success(mock_piper_voice, tmp_path):
    from backend.tts_engines.piper_engine import PiperEngine

    engine = PiperEngine()
    output_path = str(tmp_path / "output.mp3")

    # Create fake model files so exists checks pass
    voice_dir = tmp_path / "models" / "piper"
    voice_dir.mkdir(parents=True)
    (voice_dir / "en_US-lessac-medium.onnx").write_text("fake model")
    (voice_dir / "en_US-lessac-medium.onnx.json").write_text("fake config")

    with patch("backend.tts_engines.piper_engine.MODELS_DIR", tmp_path / "models"):
        result = await engine.synthesize(
            text="Hello world.",
            title="Test Article",
            author="Test Author",
            output_path=output_path,
            voice="en_US-lessac-medium",
        )

    expected_wav = output_path.replace(".mp3", ".wav")
    assert os.path.exists(expected_wav)
    assert result["filesize"] > 0
    assert result["duration"] > 0
    # Verify it's a valid WAV file
    import wave
    with wave.open(expected_wav, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 22050
        assert w.getnframes() > 0


@pytest.mark.asyncio
async def test_piper_engine_synthesize_paragraph_chunking(mock_piper_voice, tmp_path):
    """Verify that text exceeding MAX_CHUNK_CHARS is split and concatenated."""
    from backend.tts_engines.piper_engine import PiperEngine, MAX_CHUNK_CHARS

    engine = PiperEngine()
    output_path = str(tmp_path / "output.mp3")

    voice_dir = tmp_path / "models" / "piper"
    voice_dir.mkdir(parents=True)
    (voice_dir / "en_US-lessac-medium.onnx").write_text("fake model")
    (voice_dir / "en_US-lessac-medium.onnx.json").write_text("fake config")

    # Create text that requires two chunks
    long_para = "word " * (MAX_CHUNK_CHARS // 5)

    with patch("backend.tts_engines.piper_engine.MODELS_DIR", tmp_path / "models"):
        result = await engine.synthesize(
            text=long_para,
            title="Chunking Test",
            author="Tester",
            output_path=output_path,
            voice="en_US-lessac-medium",
        )

    expected_wav = output_path.replace(".mp3", ".wav")
    assert os.path.exists(expected_wav)
    assert result["filesize"] > 0
