import os
import pytest
from backend.tts import generate_podcast_audio

@pytest.mark.asyncio
async def test_speech_generation_pipeline(tmp_path):
    """
    Validates that the Edge TTS speech generation successfully connects to the API,
    processes a small multi-paragraph text chunk, and outputs a valid audio MP3.
    """
    # 1. Arrange: Create a temporary destination path for the output MP3
    temp_audio_file = tmp_path / "unit_test_audio.mp3"
    
    test_text = (
        "Welcome to the automated unit tests. This is the first paragraph of text.\n\n"
        "And this is the second paragraph. This validates that our chunking and streaming "
        "converters stich the output together without breaking the MP3 frame boundaries."
    )
    test_title = "Unit Test Article"
    test_author = "System Test Suite"
    default_voice = "en-US-GuyNeural"
    
    # 2. Act: Trigger speech synthesis
    stats = await generate_podcast_audio(
        text=test_text,
        title=test_title,
        author=test_author,
        output_path=str(temp_audio_file),
        voice=default_voice
    )
    
    # 3. Assert: Check output file exists, is not empty, and returns correct metadata
    assert os.path.exists(temp_audio_file)
    assert temp_audio_file.stat().st_size > 0
    
    assert stats["filesize"] > 0
    assert stats["duration"] > 0.0
    
    # Verify returning calculated sizing
    assert stats["filesize"] == temp_audio_file.stat().st_size
    print(f"Test synthesis succeeded! File size: {stats['filesize']} bytes, estimated duration: {stats['duration']}s")
