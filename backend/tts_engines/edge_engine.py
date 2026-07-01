import os
import logging
from typing import Dict, Any
# pyrefly: ignore [missing-import]
import edge_tts
try:
    from mutagen.mp3 import MP3 as MutagenMP3
except ImportError:
    MutagenMP3 = None

from backend.tts_engines.base import BaseTTSEngine

logger = logging.getLogger("VibeListen.EdgeEngine")


class EdgeEngine(BaseTTSEngine):
    """
    Cloud-based TTS adapter using Microsoft Edge's free Read-Aloud API via edge-tts.
    Zero-config, requires internet.
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
        """
        Asynchronously converts article text to a high-quality speech MP3 file.
        Uses a single edge_tts.Communicate call — the library handles long text
        internally via streaming.
        """
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to VibeListen. Today we are reading: {title}, by {clean_author}."
        )
        full_text = f"{intro_text}\n\n{text}"

        communicate = edge_tts.Communicate(full_text, voice)
        with open(output_path, "wb") as out_file:
            async for stream_chunk in communicate.stream():
                if stream_chunk["type"] == "audio":
                    out_file.write(stream_chunk["data"])

        filesize = os.path.getsize(output_path)

        duration = 0.0
        if MutagenMP3 is not None:
            try:
                duration = MutagenMP3(output_path).info.length
            except Exception:
                logger.debug("mutagen duration read failed, falling back to estimate")
        if not duration:
            duration = filesize / 3000.0

        return {"filesize": filesize, "duration": duration, "output_path": output_path}
