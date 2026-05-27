import os
import io
import wave
import logging
from typing import Dict, Any
from pathlib import Path

from backend.tts_engines.base import BaseTTSEngine
from backend.config import MODELS_DIR, REFERENCE_WAV_PATH

logger = logging.getLogger("PodRead.PocketEngine")

# Optional heavy dependencies - gracefully handled
try:
    import torch
except ImportError:
    torch = None

try:
    import numpy as np
except ImportError:
    np = None


class PocketEngine(BaseTTSEngine):
    """
    Kyutai Labs Pocket TTS (CALM) engine with voice cloning support.
    Requires: pip install -r requirements-pocket.txt

    Reference voice cloning:
        Place a 5-second, 24kHz mono WAV file at the path set by
        REFERENCE_WAV_PATH (default: data/models/reference.wav).
        It will be used to guide the timbre of synthesized speech.
    """

    # Expected reference audio parameters
    REF_SAMPLE_RATE = 24000
    REF_CHANNELS = 1
    REF_SAMPWIDTH = 2  # 16-bit
    REF_MAX_DURATION_SEC = 10.0
    REF_MIN_DURATION_SEC = 3.0

    def __init__(self):
        if torch is None:
            raise RuntimeError(
                "Kyutai Pocket TTS is not installed. "
                "Run: pip install -r requirements-pocket.txt"
            )
        self._model = None
        self._reference_audio = None

    def _load_model(self):
        """
        Lazily load the Pocket TTS model and reference cloning audio.
        Called on first synthesize() invocation.
        """
        if self._model is not None:
            return

        logger.info("Initializing Kyutai Pocket TTS model...")
        # ------------------------------------------------------------------
        # Placeholder for actual model loading.
        # Once dependencies are installed, replace with:
        #   from moshi.models import loaders
        #   self._model = loaders.get_pocket_model()
        # ------------------------------------------------------------------
        self._model = "placeholder_model"

        if REFERENCE_WAV_PATH.exists():
            self._validate_and_load_reference()
        else:
            logger.warning(
                f"No reference voice found at {REFERENCE_WAV_PATH}. "
                "Synthesis will use the default model voice instead of cloning."
            )

    def _validate_and_load_reference(self):
        """
        Validates the reference WAV file meets format requirements
        and loads it into memory for the cloning pipeline.
        """
        ref_path = Path(REFERENCE_WAV_PATH)
        logger.info(f"Validating reference voice: {ref_path}")

        try:
            with wave.open(str(ref_path), "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                duration = n_frames / float(framerate)

                errors = []
                if channels != self.REF_CHANNELS:
                    errors.append(
                        f"Expected {self.REF_CHANNELS} channel(s), got {channels}"
                    )
                if sampwidth != self.REF_SAMPWIDTH:
                    errors.append(
                        f"Expected {self.REF_SAMPWIDTH}-byte samples, got {sampwidth}"
                    )
                if framerate != self.REF_SAMPLE_RATE:
                    errors.append(
                        f"Expected {self.REF_SAMPLE_RATE} Hz, got {framerate} Hz"
                    )
                if duration < self.REF_MIN_DURATION_SEC:
                    errors.append(
                        f"Reference too short ({duration:.2f}s < {self.REF_MIN_DURATION_SEC}s)"
                    )
                if duration > self.REF_MAX_DURATION_SEC:
                    errors.append(
                        f"Reference too long ({duration:.2f}s > {self.REF_MAX_DURATION_SEC}s)"
                    )

                if errors:
                    raise ValueError("; ".join(errors))

                raw_bytes = wf.readframes(n_frames)
                # Convert to float32 tensor normalized to [-1, 1]
                if np is None:
                    raise RuntimeError(
                        "numpy is required for reference voice processing. "
                        "Run: pip install -r requirements-pocket.txt"
                    )
                samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
                samples /= np.iinfo(np.int16).max
                self._reference_audio = torch.from_numpy(samples)

                logger.info(
                    f"Reference voice loaded: {duration:.2f}s, "
                    f"{framerate} Hz, {channels} channel(s)"
                )

        except wave.Error as exc:
            raise RuntimeError(
                f"Reference file {ref_path} is not a valid WAV: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load reference voice from {ref_path}: {exc}"
            ) from exc

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
        Synthesize text to speech using Kyutai Pocket TTS.
        If a valid reference voice is configured, voice cloning will be applied.
        """
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to PodRead. Today we are reading: {title}, by {clean_author}."
        )
        full_text = f"{intro_text}\n\n{text}"

        self._load_model()

        # ------------------------------------------------------------------
        # Placeholder for actual synthesis pipeline.
        # Once dependencies are installed, replace with:
        #   audio_tensor = self._model.generate(
        #       text=full_text,
        #       reference_audio=self._reference_audio,
        #       voice=voice,
        #   )
        #   write_tensor_to_file(audio_tensor, output_path)
        # ------------------------------------------------------------------
        raise NotImplementedError(
            "Kyutai Pocket TTS synthesis is not yet fully implemented. "
            "Install requirements-pocket.txt and wire the real model calls "
            "in backend/tts_engines/pocket_engine.py."
        )

        # The code below shows the intended production flow once wired:
        # filesize = os.path.getsize(output_path)
        # estimated_duration = filesize / 44100.0
        # return {"filesize": filesize, "duration": estimated_duration}
