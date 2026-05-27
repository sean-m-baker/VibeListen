from typing import Dict, Any
from backend.tts_engines import get_tts_engine


async def generate_podcast_audio(
    text: str, title: str, author: str, output_path: str, voice: str, engine_name: str = None
) -> Dict[str, Any]:
    """
    Unified podcast audio generator.
    Delegates to the pluggable TTS engine configured via the TTS_ENGINE env variable
    or overridden by the engine_name parameter.
    """
    engine = get_tts_engine(engine_name)
    return await engine.synthesize(
        text=text,
        title=title,
        author=author,
        output_path=output_path,
        voice=voice,
    )
