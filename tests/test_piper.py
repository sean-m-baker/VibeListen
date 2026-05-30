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
        mock_instance.synthesize.return_value = [b"audio_chunk_1", b"audio_chunk_2"]
        mock_instance.sample_rate = 22050
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

    with patch("backend.tts_engines.piper_engine.ensure_piper_voice") as mock_ensure:
        mock_ensure.return_value = Path("/fake/model.onnx")

        with patch("backend.tts_engines.piper_engine.AudioSegment") as MockAudio:
            mock_segment = MagicMock()
            
            def create_file_on_export(*args, **kwargs):
                # Actually create the output file so os.path.getsize works
                Path(args[0]).write_text("fake mp3 content")
            
            mock_segment.export.side_effect = create_file_on_export
            MockAudio.from_wav.return_value = mock_segment

            result = await engine.synthesize(
                text="Hello world.",
                title="Test Article",
                author="Test Author",
                output_path=output_path,
                voice="en_US-lessac-medium",
            )

    assert result["filesize"] >= 0
    MockAudio.from_wav.assert_called_once()
    mock_segment.export.assert_called_once_with(output_path, format="mp3", bitrate="128k")


@pytest.mark.asyncio
async def test_piper_engine_synthesize_no_pydub(mock_piper_voice, tmp_path):
    from backend.tts_engines.piper_engine import PiperEngine

    engine = PiperEngine()
    output_path = str(tmp_path / "output.mp3")

    with patch("backend.tts_engines.piper_engine.ensure_piper_voice") as mock_ensure:
        mock_ensure.return_value = Path("/fake/model.onnx")

        with patch("backend.tts_engines.piper_engine.AudioSegment", None):
            result = await engine.synthesize(
                text="Hello world.",
                title="Test Article",
                author="Test Author",
                output_path=output_path,
                voice="en_US-lessac-medium",
            )

    assert result["filesize"] >= 0
    # With no pydub, it should fall back to .wav
    assert os.path.exists(output_path.replace(".mp3", ".wav"))
