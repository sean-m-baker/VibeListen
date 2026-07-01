import io
import wave
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from backend.config import REFERENCE_WAV_PATH


def _make_valid_wav(path: Path, duration_sec: float = 5.0, sample_rate: int = 24000):
    n_frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


@pytest.fixture
def mock_tts_model():
    """Mock the entire TTSModel returned by get_default_tts_model."""
    with patch("backend.tts_engines.pocket_engine.get_default_tts_model") as mock_get:
        tts = MagicMock()
        tts.voice_suffix = ".sig@0.safetensors"
        tts.simple_generate.return_value = [MagicMock()]
        tts.simple_generate.return_value[0].cpu.return_value.numpy.return_value = (
            b"\x00\x00".__mul__(24000)
        )
        mock_get.return_value = tts
        yield tts


def test_pocket_engine_init(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()
    assert engine._tts is None
    assert engine._device in ("cpu", "cuda")


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_default(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine, hf_hub_download
    engine = PocketEngine()
    engine._tts = mock_tts_model

    async def mock_available_voices():
        return ["alice"]

    with patch.object(engine, "_available_voices", mock_available_voices):
        with patch("backend.tts_engines.pocket_engine.hf_hub_download") as mock_dl:
            mock_dl.return_value = "/fake/path/to/alice.sig@0.safetensors"
            result = await engine._voice_to_path("default")
            assert result == "/fake/path/to/alice.sig@0.safetensors"
            mock_dl.assert_called_once_with(
                repo_id="kyutai/tts-voices", filename="alice.sig@0.safetensors"
            )


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_cloned_missing_file(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()
    engine._tts = mock_tts_model

    with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", Path("/nonexistent/ref.wav")):
        with pytest.raises(RuntimeError, match="No reference audio uploaded"):
            await engine._voice_to_path("cloned")


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_cloned_valid(mock_tts_model, tmp_path):
    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()
    engine._tts = mock_tts_model

    ref = tmp_path / "ref.wav"
    _make_valid_wav(ref, duration_sec=5.0, sample_rate=24000)
    with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref):
        result = await engine._voice_to_path("cloned")
    assert result == str(ref.resolve())


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_unknown(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine, hf_hub_download
    engine = PocketEngine()
    engine._tts = mock_tts_model

    async def mock_available_voices():
        return []

    with patch.object(engine, "_available_voices", mock_available_voices):
        with patch("backend.tts_engines.pocket_engine.hf_hub_download") as mock_dl:
            mock_dl.side_effect = Exception("Not found")
            with pytest.raises(RuntimeError, match="Voice 'nonexistent_voice' not found"):
                await engine._voice_to_path("nonexistent_voice")


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_named_success(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine, hf_hub_download
    engine = PocketEngine()
    engine._tts = mock_tts_model

    async def mock_available_voices():
        return []

    with patch.object(engine, "_available_voices", mock_available_voices):
        with patch("backend.tts_engines.pocket_engine.hf_hub_download") as mock_dl:
            mock_dl.return_value = "/fake/alice.safetensors"
            result = await engine._voice_to_path("alice")
    assert result == "/fake/alice.safetensors"
    mock_dl.assert_called_once_with(repo_id="kyutai/tts-voices", filename="alice.sig@0.safetensors")


@pytest.mark.asyncio
async def test_pocket_engine_voice_to_path_not_loaded():
    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()
    with pytest.raises(RuntimeError, match="Model not loaded"):
        await engine._voice_to_path("default")


@pytest.mark.asyncio
async def test_available_voices_network_failure(mock_tts_model):
    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()
    engine._tts = mock_tts_model

    with patch("backend.tts_engines.pocket_engine.list_repo_files") as mock_list:
        mock_list.side_effect = Exception("Network error")
        voices = await engine._available_voices()
    assert voices == []


@pytest.mark.asyncio
async def test_synthesize_empty_result(mock_tts_model, tmp_path):
    mock_tts_model.simple_generate.return_value = []

    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()

    async def mock_vtp(*args):
        return "/fake/path"

    with patch.object(engine, "_voice_to_path", mock_vtp):
        with pytest.raises(RuntimeError, match="returned empty result"):
            await engine.synthesize(
                text="Hello.", title="Test", author="Tester",
                output_path=str(tmp_path / "o.mp3"), voice="default",
            )


@pytest.mark.asyncio
async def test_pocket_engine_synthesize_default_voice(mock_tts_model, tmp_path):
    import numpy as np
    fake_wav = np.zeros(48000, dtype=np.float32)
    mock_tts_model.simple_generate.return_value = [
        MagicMock(cpu=lambda: MagicMock(numpy=lambda: fake_wav))
    ]

    from backend.tts_engines.pocket_engine import PocketEngine
    engine = PocketEngine()

    async def mock_voices():
        return ["alice"]
    async def mock_vtp(*a):
        return "/fake/alice.safetensors"

    with patch.object(engine, "_available_voices", mock_voices):
        with patch.object(engine, "_voice_to_path", mock_vtp):
            output_path = str(tmp_path / "output.mp3")
            result = await engine.synthesize(
                text="Hello world.",
                title="Test Article",
                author="Test Author",
                output_path=output_path,
                voice="default",
            )

    expected_wav = output_path.replace(".mp3", ".wav")
    assert Path(expected_wav).exists()
    assert result["filesize"] > 0
    assert result["duration"] == pytest.approx(2.0, rel=0.1)
    mock_tts_model.simple_generate.assert_called_once()


@pytest.mark.asyncio
async def test_pocket_engine_synthesize_cloned_voice(mock_tts_model, tmp_path):
    import numpy as np
    fake_wav = np.zeros(48000, dtype=np.float32)
    mock_tts_model.simple_generate.return_value = [
        MagicMock(cpu=lambda: MagicMock(numpy=lambda: fake_wav))
    ]

    ref = tmp_path / "ref.wav"
    _make_valid_wav(ref, duration_sec=5.0, sample_rate=24000)

    with patch("backend.tts_engines.pocket_engine.REFERENCE_WAV_PATH", ref):
        from backend.tts_engines.pocket_engine import PocketEngine
        engine = PocketEngine()
        output_path = str(tmp_path / "output.mp3")

        result = await engine.synthesize(
            text="Hello world.",
            title="Test Article",
            author="Test Author",
            output_path=output_path,
            voice="cloned",
        )

    expected_wav = output_path.replace(".mp3", ".wav")
    assert Path(expected_wav).exists()
    assert result["filesize"] > 0
    assert result["duration"] > 0
    mock_tts_model.simple_generate.assert_called_once()
