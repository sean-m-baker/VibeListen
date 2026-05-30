from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTTSEngine(ABC):
    """
    Abstract base class for all text-to-speech engines (Edge TTS, Piper, Pocket, etc.).
    Ensures every adapter exposes a unified async synthesize() interface.
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        title: str,
        author: str,
        output_path: str,
        voice: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Converts article text into a podcast-ready MP3 audio file.

        Args:
            text: Clean plain-text article content.
            title: Article title for the intro.
            author: Article author for the intro.
            output_path: Absolute file path where the MP3 should be written.
            voice: Identifier string for the voice (varies by engine).
            **kwargs: Engine-specific runtime overrides (e.g. reference_cloning_path).

        Returns:
            Dictionary with at minimum 'filesize' (bytes) and 'duration' (seconds).
        """
        ...
