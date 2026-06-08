import os
import wave
import io
import logging
from typing import Dict, Any, List
from pathlib import Path

from backend.tts_engines.base import BaseTTSEngine
from backend.config import MODELS_DIR

logger = logging.getLogger("VibeListen.PiperEngine")

# Optional heavy dependency - imported lazily inside methods
try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None

try:
    from piper.download_voices import download_voice
except ImportError:
    download_voice = None

MAX_CHUNK_CHARS = 2000


def _read_wav_data(wav_bytes: bytes) -> tuple[int, int, int, bytes]:
    """Parse WAV bytes and return (channels, sample_width, framerate, audio_data)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes()))


def _build_wav(channels: int, sample_width: int, framerate: int, audio_data: bytes) -> bytes:
    """Build a complete WAV file from raw audio parameters and data."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(framerate)
        w.writeframes(audio_data)
    return buf.getvalue()


def _concatenate_wavs(chunks: List[bytes]) -> bytes:
    """Concatenate multiple same-format WAV byte streams into one."""
    if not chunks:
        return b""
    if len(chunks) == 1:
        return chunks[0]

    ref = _read_wav_data(chunks[0])
    channels, sample_width, framerate = ref[0], ref[1], ref[2]
    all_audio = bytearray(ref[3])

    for chunk in chunks[1:]:
        c = _read_wav_data(chunk)
        if (c[0], c[1], c[2]) != (channels, sample_width, framerate):
            logger.warning("WAV format mismatch between chunks, using first chunk's format")
        all_audio.extend(c[3])

    return _build_wav(channels, sample_width, framerate, bytes(all_audio))


class PiperEngine(BaseTTSEngine):
    """
    Local ONNX-backed Piper TTS engine.
    Requires: pip install -r requirements-piper.txt
    """

    def __init__(self):
        if PiperVoice is None:
            raise RuntimeError(
                "Piper TTS is not installed. Run: pip install -r requirements-piper.txt"
            )
        self._voice_cache: Dict[str, PiperVoice] = {}

    def _get_voice(self, voice_name: str) -> "PiperVoice":
        """Load and cache a PiperVoice instance."""
        if voice_name in self._voice_cache:
            return self._voice_cache[voice_name]

        voice_dir = MODELS_DIR / "piper"
        voice_dir.mkdir(parents=True, exist_ok=True)

        model_path = voice_dir / f"{voice_name}.onnx"
        config_path = voice_dir / f"{voice_name}.onnx.json"

        if not (model_path.exists() and config_path.exists()):
            if download_voice is not None:
                logger.info(f"Downloading Piper voice '{voice_name}'...")
                download_voice(voice_name, voice_dir, force_redownload=False)
            else:
                raise RuntimeError(
                    f"Piper voice '{voice_name}' not found and piper's download "
                    f"utility is unavailable. Manually place the .onnx and .onnx.json "
                    f"files in {voice_dir}."
                )

        if not model_path.exists():
            raise RuntimeError(
                f"Piper voice '{voice_name}' not found and could not be downloaded. "
                f"Check your internet connection or manually place the .onnx and .onnx.json "
                f"files in {voice_dir}."
            )

        logger.info(f"Loading Piper voice: {model_path}")
        voice = PiperVoice.load(str(model_path))
        self._voice_cache[voice_name] = voice
        return voice

    def _synthesize_chunk(self, voice, text: str) -> bytes:
        """Synthesize a single text chunk and return the WAV bytes."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return buf.getvalue()

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
        Synthesize text to speech using Piper TTS.
        Chunks long text to avoid excessive per-call latency.
        Outputs WAV (MP3 conversion requires pydub+ffmpeg).
        """
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to VibeListen. Today we are reading: {title}, by {clean_author}."
        )

        voice_instance = self._get_voice(voice)

        paragraphs = text.split("\n\n")
        text_chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            if len(p) > MAX_CHUNK_CHARS:
                if current_chunk:
                    text_chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                start = 0
                while start < len(p):
                    end = min(start + MAX_CHUNK_CHARS, len(p))
                    if end < len(p):
                        last_space = p.rfind(" ", start, end)
                        if last_space > start:
                            end = last_space
                    text_chunks.append(p[start:end])
                    start = end
                continue

            if current_length + len(p) > MAX_CHUNK_CHARS:
                text_chunks.append("\n\n".join(current_chunk))
                current_chunk = [p]
                current_length = len(p)
            else:
                current_chunk.append(p)
                current_length += len(p) + 2

        if current_chunk:
            text_chunks.append("\n\n".join(current_chunk))

        wav_chunks: List[bytes] = []

        for idx, chunk_text in enumerate(text_chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            if idx == 0:
                chunk_text = f"{intro_text}\n\n{chunk_text}"

            logger.debug(f"Synthesizing chunk {idx + 1}/{len(text_chunks)} ({len(chunk_text)} chars)")
            wav_bytes = self._synthesize_chunk(voice_instance, chunk_text)
            wav_chunks.append(wav_bytes)

        combined_wav = _concatenate_wavs(wav_chunks)

        wav_path = str(Path(output_path).with_suffix(".wav"))
        with open(wav_path, "wb") as f:
            f.write(combined_wav)

        filesize = os.path.getsize(wav_path)
        with wave.open(wav_path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            estimated_duration = frames / rate

        return {"filesize": filesize, "duration": estimated_duration}
