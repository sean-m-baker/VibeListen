import os
from typing import Dict, Any
from backend.tts_engines import get_tts_engine


async def generate_podcast_audio(
    text: str,
    title: str,
    author: str,
    output_path: str,
    voice: str,
    engine_name: str = "edge",
    **kwargs,
) -> Dict[str, Any]:
    """
    Converts article text to a podcast-ready MP3 file using the configured TTS engine.

    Delegates to the pluggable engine factory so that Edge, Piper, or Pocket TTS
    can be selected without modifying this entrypoint.

    Returns a dictionary with 'filesize' (bytes) and 'duration' (seconds).
    """
    engine = get_tts_engine(engine_name)
    return await engine.synthesize(
        text=text,
        title=title,
        author=author,
        output_path=output_path,
        voice=voice,
        **kwargs,
    )
