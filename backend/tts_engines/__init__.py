import logging
from typing import Optional, Type

from backend.config import TTS_ENGINE
from backend.tts_engines.base import BaseTTSEngine

logger = logging.getLogger("VibeListen.TTS.Factory")


# ============================================================================
# Engine Registry
# ============================================================================

# Lazy import wrappers so optional heavy packages are not touched at import time

def _build_edge_engine() -> Type[BaseTTSEngine]:
    from backend.tts_engines.edge_engine import EdgeEngine
    return EdgeEngine


def _build_piper_engine() -> Type[BaseTTSEngine]:
    try:
        from piper import PiperVoice  # noqa: F401 – verify package is available
    except ImportError as exc:
        raise RuntimeError(
            "Piper TTS is not installed. Install Piper deps: "
            "pip install -r requirements-piper.txt"
        ) from exc
    from backend.tts_engines.piper_engine import PiperEngine
    return PiperEngine


def _build_pocket_engine() -> Type[BaseTTSEngine]:
    try:
        import torch  # noqa: F401 – verify package is available
    except ImportError as exc:
        raise RuntimeError(
            "Kyutai Pocket TTS dependencies are not installed. "
            "Install Pocket deps: pip install -r requirements-pocket.txt"
        ) from exc
    from backend.tts_engines.pocket_engine import PocketEngine
    return PocketEngine


_ENGINE_BUILDERS = {
    "edge": _build_edge_engine,
    "piper": _build_piper_engine,
    "pocket": _build_pocket_engine,
}


# ============================================================================
# Public API
# ============================================================================

def get_tts_engine(engine_name: Optional[str] = None) -> BaseTTSEngine:
    """
    Returns a fully instantiated TTS engine based on the supplied name or the
    global TTS_ENGINE env variable.

    Raises:
        ValueError: If the requested engine name does not exist.
        RuntimeError: If the engine exists but its optional dependency set is
            not installed.
    """
    name = (engine_name or TTS_ENGINE).strip().lower()

    if name not in _ENGINE_BUILDERS:
        valid = ", ".join(_ENGINE_BUILDERS.keys())
        logger.error(f"Invalid TTS engine requested: '{name}'. Valid: {valid}")
        raise ValueError(
            f"Invalid TTS engine '{name}'. Choose one of: {valid}"
        )

    engine_cls = _ENGINE_BUILDERS[name]()
    logger.info(f"TTS engine '{name}' loaded successfully.")
    return engine_cls()


def list_available_engines() -> dict:
    """
    Returns a mapping of registered engine names to a boolean indicating whether
    the engine is installable / importable on this machine.
    """
    availability = {}
    for name, builder in _ENGINE_BUILDERS.items():
        try:
            builder()
            availability[name] = True
        except RuntimeError:
            availability[name] = False
    return availability
