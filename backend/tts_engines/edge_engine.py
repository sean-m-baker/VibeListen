import os
from typing import Dict, Any
# pyrefly: ignore [missing-import]
import edge_tts

from backend.tts_engines.base import BaseTTSEngine


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
        Chunks by paragraphs to prevent timeouts on long articles.
        """
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to VibeListen. Today we are reading: {title}, by {clean_author}."
        )

        paragraphs = text.split("\n\n")
        chunks = [intro_text]
        current_chunk = []
        current_length = 0

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if current_length + len(p) > 4000:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [p]
                current_length = len(p)
            else:
                current_chunk.append(p)
                current_length += len(p) + 2

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        with open(output_path, "wb") as out_file:
            for index, chunk_text in enumerate(chunks):
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue

                communicate = edge_tts.Communicate(chunk_text, voice)
                async for stream_chunk in communicate.stream():
                    if stream_chunk["type"] == "audio":
                        out_file.write(stream_chunk["data"])

        filesize = os.path.getsize(output_path)
        estimated_duration = filesize / 3000.0

        return {"filesize": filesize, "duration": estimated_duration}
