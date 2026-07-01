from __future__ import annotations

import os
import time
import logging
import threading
from typing import Dict, Any
from pathlib import Path

import sphn
import torch
import numpy as np

from backend.tts_engines.base import BaseTTSEngine
from backend.config import REFERENCE_WAV_PATH
from moshi.models.tts import get_default_tts_model
from huggingface_hub import hf_hub_download, list_repo_files

logger = logging.getLogger("VibeListen.PocketEngine")

SAMPLE_RATE = 24000
VOICE_REPO = "kyutai/tts-voices"
_VOICES_CACHE: list[str] | None = None
_VOICES_CACHE_TIME: float = 0
_VOICES_CACHE_TTL = 300
_VOICES_CACHE_LOCK = threading.Lock()


class PocketEngine(BaseTTSEngine):
    """
    Kyutai Labs Pocket TTS (CALM) engine with voice cloning support.
    Uses the Kyutai Moshi TTS model (DSM-based).

    Voice options:
        "default" — uses the first available voice from the HF repo.
        "cloned" — uses the uploaded reference WAV for voice cloning.
        Any other value — treated as a voice name to download from the
        HuggingFace voice repo (kyutai/tts-voices).
    """

    def __init__(self):
        self._tts: Any = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._lock = threading.Lock()
        # Limit PyTorch CPU threads to prevent 100% core utilisation during
        # inference, which starves the web server and launcher process.
        torch.set_num_threads(max(1, os.cpu_count() // 2 or 1))

    def _load_model(self):
        if self._tts is not None:
            return
        with self._lock:
            if self._tts is not None:
                return
            logger.info(f"Loading Pocket TTS model (device={self._device})...")
            self._tts = get_default_tts_model(n_q=32, device=self._device)
            logger.info("Pocket TTS model loaded.")

    async def _available_voices(self) -> list[str]:
        global _VOICES_CACHE, _VOICES_CACHE_TIME
        now = time.monotonic()
        if _VOICES_CACHE is not None and (now - _VOICES_CACHE_TIME) < _VOICES_CACHE_TTL:
            return _VOICES_CACHE
        with _VOICES_CACHE_LOCK:
            if _VOICES_CACHE is not None and (now - _VOICES_CACHE_TIME) < _VOICES_CACHE_TTL:
                return _VOICES_CACHE
            try:
                if self._tts is None:
                    self._load_model()
                import asyncio
                files = await asyncio.to_thread(list_repo_files, VOICE_REPO)
                suffix = self._tts.voice_suffix
                names = set()
                for f in files:
                    if suffix and f.endswith(suffix):
                        names.add(f[: -len(suffix)])
                _VOICES_CACHE = sorted(names)
                _VOICES_CACHE_TIME = time.monotonic()
                return _VOICES_CACHE
            except Exception:
                return _VOICES_CACHE or []

    async def _voice_to_path(self, voice: str) -> str:
        if self._tts is None:
            raise RuntimeError("Model not loaded. Call _load_model() first.")

        if voice == "cloned":
            ref = Path(REFERENCE_WAV_PATH)
            if not ref.exists():
                raise RuntimeError(
                    "No reference audio uploaded. Upload a 5-second, "
                    "24kHz mono WAV in Settings first."
                )
            return str(ref.resolve())

        if voice == "default":
            voices = await self._available_voices()
            if not voices:
                raise RuntimeError(
                    "No default voices available. Upload a reference WAV and use 'cloned' voice."
                )
            voice = voices[0]

        suffix = self._tts.voice_suffix
        import asyncio
        try:
            local = await asyncio.to_thread(
                hf_hub_download,
                repo_id=VOICE_REPO,
                filename=voice + suffix,
            )
            return local
        except Exception as exc:
            available = await self._available_voices()
            msg = f"Voice '{voice}' not found in {VOICE_REPO}."
            if available:
                msg += f" Available: {', '.join(available[:10])}"
            raise RuntimeError(msg) from exc

    async def available_voice_names(self) -> list[str]:
        return await self._available_voices()

    async def synthesize(
        self,
        text: str,
        title: str,
        author: str,
        output_path: str,
        voice: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        clean_author = (
            author if author and author.lower() != "unknown" else "an unknown author"
        )
        intro_text = (
            f"Welcome to VibeListen. Today we are reading: {title}, by {clean_author}."
        )
        full_text = f"{intro_text}\n\n{text}"

        self._load_model()

        voice_path = await self._voice_to_path(voice)
        logger.info(f"Synthesizing with Pocket TTS (voice={voice})...")
        import asyncio
        pcms = await asyncio.to_thread(
            self._tts.simple_generate, full_text, voice_path, show_progress=False
        )
        if not pcms:
            raise RuntimeError("Pocket TTS synthesis returned empty result.")
        wav = pcms[0].cpu().numpy()

        wav_path = str(Path(output_path).with_suffix(".wav"))
        sphn.write_wav(wav_path, wav, SAMPLE_RATE)

        filesize = os.path.getsize(wav_path)
        estimated_duration = wav.shape[-1] / SAMPLE_RATE
        return {"filesize": filesize, "duration": estimated_duration, "output_path": wav_path}
