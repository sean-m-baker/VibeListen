import os
import pytest

from backend.tts_engines.base import BaseTTSEngine
from backend.tts_engines import get_tts_engine, list_available_engines


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure TTS_ENGINE env is clean before each test."""
    old = os.environ.pop("TTS_ENGINE", None)
    yield
    if old is not None:
        os.environ["TTS_ENGINE"] = old


def test_get_valid_edge_engine():
    """Factory should return a working EdgeEngine when TTS_ENGINE=edge."""
    engine = get_tts_engine("edge")
    assert isinstance(engine, BaseTTSEngine)


def test_get_invalid_engine_raises():
    """Factory should raise ValueError with descriptive message for unknown engines."""
    with pytest.raises(ValueError, match="Invalid TTS engine 'nonsense'"):
        get_tts_engine("nonsense")


def test_get_piper_engine_without_deps_raises_gracefully():
    """
    If piper-tts package is NOT installed, requesting 'piper' should raise
    RuntimeError pointing to the specific requirements-piper.txt file.
    """
    with pytest.raises(RuntimeError, match="pip install -r requirements-piper.txt"):
        get_tts_engine("piper")


def test_get_pocket_engine_without_deps_raises_gracefully():
    """
    If torch package is NOT installed, requesting 'pocket' should raise
    RuntimeError pointing to the specific requirements-pocket.txt file.
    """
    with pytest.raises(RuntimeError, match="pip install -r requirements-pocket.txt"):
        get_tts_engine("pocket")


def test_list_available_engines():
    """
    list_available_engines should identify the current machine's capabilities.
    Edge is always available; Piper and Pocket depend on heavy deps.
    """
    avail = list_available_engines()
    assert avail["edge"] is True
    assert isinstance(avail["piper"], bool)
    assert isinstance(avail["pocket"], bool)
