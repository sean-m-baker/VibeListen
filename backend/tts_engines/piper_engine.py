import os
import wave
import io
import logging
from typing import Dict, Any
from pathlib import Path

from backend.tts_engines.base import BaseTTSEngine
from backend.config import MODELS_DIR
from backend.utils.downloader import ensure_piper_voice

logger = logging.getLogger("PodRead.PiperEngine")

# Optional heavy dependency - imported lazily inside methods
try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None


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

        model_path = ensure_piper_voice(voice_name, MODELS_DIR)
        if model_path is None:
            raise RuntimeError(
                f"Piper voice '{voice_name}' not found and could not be downloaded. "
                f"Check your internet connection or manually place the .onnx and .onnx.json "
                f"files in {MODELS_DIR / 'piper'}."
            )

        logger.info(f"Loading Piper voice: {model_path}")
        voice = PiperVoice.load(str(model_path))
        self._voice_cache[voice_name] = voice
        return voice

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
        Outputs MP3 by first generating WAV then transcoding.
        """
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to PodRead. Today we are reading: {title}, by {clean_author}."
        )
        full_text = f"{intro_text}\n\n{text}"

        voice_instance = self._get_voice(voice)

        # Generate WAV in-memory with correct Piper parameters
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(voice_instance.sample_rate)
            # Piper synthesize is a generator of audio bytes
            for audio_bytes in voice_instance.synthesize(full_text):
                wav_file.writeframes(audio_bytes)

        wav_buffer.seek(0)

        # Transcode to MP3 using pydub if available
        if AudioSegment is not None:
            audio = AudioSegment.from_wav(wav_buffer)
            audio.export(output_path, format="mp3", bitrate="128k")
        else:
            # Fallback: write raw WAV and hope the player supports it
            logger.warning(
                "pydub not installed. Outputting WAV instead of MP3. "
                "Install with: pip install pydub ffmpeg-python"
            )
            wav_path = output_path.replace(".mp3", ".wav")
            with open(wav_path, "wb") as f:
                f.write(wav_buffer.read())
            output_path = wav_path

        filesize = os.path.getsize(output_path)
        # Estimate duration: 22050 Hz sample rate, 16-bit mono = 44100 bytes/sec
        estimated_duration = filesize / 44100.0

        return {"filesize": filesize, "duration": estimated_duration}
