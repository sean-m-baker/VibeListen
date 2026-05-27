from typing import Dict, Any
from backend.tts_engines.base import BaseTTSEngine


class PiperEngine(BaseTTSEngine):
    """
    Placeholder for local ONNX-backed Piper TTS engine.
    Will be fully implemented in Feature 3 (Phase 2).
    """

    async def synthesize(
        self,
        text: str,
        title: str,
        author: str,
        output_path: str,
        voice: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "Piper TTS synthesis is not yet implemented. "
            "Expected completion in Phase 2 Feature 3."
        )
