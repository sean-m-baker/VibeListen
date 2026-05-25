from typing import Dict, Any
from backend.tts_engines import get_tts_engine


async def generate_podcast_audio(text: str, title: str, author: str, output_path: str, voice: str) -> Dict[str, Any]:
    """
    Asynchronously converts article text to a high-quality speech MP3 file.
    To prevent network timeouts on long articles, it chunks the text by
    paragraphs and streams the resulting MP3 audio sequentially into a single file.
    
    Returns a dictionary with 'filesize' (bytes) and 'duration' (seconds).
    """
    # Create a friendly introductory header for the podcast track
    clean_author = author if author and author.lower() != "unknown" else "an unknown author"
    intro_text = f"Welcome to VibeListen. Today we are reading: {title}, by {clean_author}."

    # Split original article by paragraphs to maintain speech pauses
    paragraphs = text.split("\n\n")
    
    chunks = [intro_text]
    current_chunk = []
    current_length = 0
    
    # Group paragraphs into chunks of ~4000 characters to prevent Edge TTS timeouts
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
            current_length += len(p) + 2  # account for double newline

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Stream and write audio chunks directly into the final MP3 file
    # Direct binary concatenation works perfectly for MP3 files since they consist of independent frames.
    with open(output_path, "wb") as out_file:
        for index, chunk_text in enumerate(chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            
            communicate = edge_tts.Communicate(chunk_text, voice)
            async for stream_chunk in communicate.stream():
                if stream_chunk["type"] == "audio":
                    out_file.write(stream_chunk["data"])

    # Retrieve final file properties
    filesize = os.path.getsize(output_path)
    
    # Edge TTS default MP3 audio uses a constant bit rate (CBR) of 24kbps mono.
    # 24 kbps = 24,000 bits per second = 3,000 bytes per second.
    # Therefore, duration (seconds) = file size (bytes) / 3,000.
    estimated_duration = filesize / 3000.0

    return {
        "filesize": filesize,
        "duration": estimated_duration
    }
