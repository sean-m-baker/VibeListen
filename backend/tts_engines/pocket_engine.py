from typing import Dict, Any
from backend.tts_engines.base import BaseTTSEngine


class PocketEngine(BaseTTSEngine):
    """
    Placeholder for Kyutai Labs Pocket TTS (CALM) engine.
    Will be fully implemented in Feature 4 (Phase 2).
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
            "Kyutai Pocket TTS synthesis is not yet implemented. "
            "Expected completion in Phase 2 Feature 4."
        )
