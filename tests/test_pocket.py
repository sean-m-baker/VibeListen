import io
import wave
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.config import REFERENCE_WAV_PATH


def _make_valid_wav(path: Path, duration_sec: float = 5.0, sample_rate: int = 24000):
    """Generate a minimal valid mono 16-bit WAV file."""
    n_frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


def _mock_numpy():
    """Return a MagicMock that mimics the numpy operations we need."""
    mock_np = MagicMock()
    mock_np.int16 = "int16"
    mock_np.float32 = "float32"
    mock_np.iinfo.return_value.max = 32767

    def fake_frombuffer(data, dtype):
        # Return a simple array-like mock
        arr = MagicMock()
        arr.astype.return_value = arr
        arr.__truediv__ = lambda self, other: self
        return arr

    mock_np.frombuffer = fake_frombuffer
    return mock_np


def test_pocket_engine_missing_dependency():
    with patch("backend.tts_engines.pocket_engine.torch", None):
        from backend.tts_engines.pocket_engine import PocketEngine
        with pytest.raises(RuntimeError, match="Kyutai Pocket TTS is not installed"):
            PocketEngine()


def test_reference_validation_valid(tmp_path):
    ref_path = tmp_path / "reference.wav"
    _make_valid_wav(ref_path, duration_sec=5.0, sample_rate=24000)

    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref_path):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                # _load_model triggers validation
                engine._load_model()
                assert engine._reference_audio is not None


def test_reference_validation_too_short(tmp_path):
    ref_path = tmp_path / "reference.wav"
    _make_valid_wav(ref_path, duration_sec=1.0, sample_rate=24000)

    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref_path):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                with pytest.raises(RuntimeError, match="Reference too short"):
                    engine._load_model()


def test_reference_validation_too_long(tmp_path):
    ref_path = tmp_path / "reference.wav"
    _make_valid_wav(ref_path, duration_sec=15.0, sample_rate=24000)

    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref_path):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                with pytest.raises(RuntimeError, match="Reference too long"):
                    engine._load_model()


def test_reference_validation_wrong_sample_rate(tmp_path):
    ref_path = tmp_path / "reference.wav"
    _make_valid_wav(ref_path, duration_sec=5.0, sample_rate=16000)

    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref_path):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                with pytest.raises(RuntimeError, match="Expected 24000 Hz"):
                    engine._load_model()


def test_reference_validation_invalid_file(tmp_path):
    ref_path = tmp_path / "reference.wav"
    ref_path.write_text("this is not a wav file")

    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref_path):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                with pytest.raises(RuntimeError, match="not a valid WAV"):
                    engine._load_model()


@pytest.mark.asyncio
async def test_pocket_engine_synthesize_not_implemented(tmp_path):
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        from backend.tts_engines.pocket_engine import PocketEngine
        engine = PocketEngine()
        output_path = str(tmp_path / "output.mp3")

        with pytest.raises(NotImplementedError, match="not yet fully implemented"):
            await engine.synthesize(
                text="Hello world.",
                title="Test Article",
                author="Test Author",
                output_path=output_path,
                voice="default",
            )


def test_reference_validation_missing_file():
    mock_np = _mock_numpy()
    with patch("backend.tts_engines.pocket_engine.torch", MagicMock()):
        with patch("backend.tts_engines.pocket_engine.np", mock_np):
            # Point to a non-existent path
            with patch(
                "backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH",
                Path("/nonexistent/reference.wav"),
            ):
                from backend.tts_engines.pocket_engine import PocketEngine
                engine = PocketEngine()
                # Missing reference should load model but keep _reference_audio as None
                engine._load_model()
                assert engine._reference_audio is None
                assert engine._model is not None
