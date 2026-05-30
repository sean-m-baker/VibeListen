import os
import logging
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger("VibeListen.Downloader")

# Default HuggingFace repository for Piper voices
PIPER_VOICES_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def download_file(url: str, dest_path: Path, chunk_size: int = 8192) -> bool:
    """
    Downloads a file from url to dest_path with streaming and basic validation.
    Returns True on success, False on failure.
    """
    logger.info(f"Downloading {url} -> {dest_path}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

        if total_size > 0 and downloaded != total_size:
            logger.error(
                f"Download incomplete: expected {total_size} bytes, got {downloaded}"
            )
            dest_path.unlink(missing_ok=True)
            return False

        logger.info(f"Download complete: {dest_path} ({downloaded} bytes)")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        return False


def ensure_piper_voice(voice_name: str, models_dir: Path) -> Optional[Path]:
    """
    Ensures both the .onnx model and .onnx.json config exist for a given Piper voice.
    If missing, attempts to download them from the default HuggingFace repository.

    Returns the path to the .onnx model file, or None if unavailable.
    """
    voice_dir = models_dir / "piper"
    voice_dir.mkdir(parents=True, exist_ok=True)

    model_path = voice_dir / f"{voice_name}.onnx"
    config_path = voice_dir / f"{voice_name}.onnx.json"

    # Check if both files already exist
    if model_path.exists() and config_path.exists():
        logger.info(f"Piper voice '{voice_name}' found locally.")
        return model_path

    # Download missing files
    base_url = f"{PIPER_VOICES_BASE_URL}/{voice_name}"
    
    success = True
    if not model_path.exists():
        success = download_file(f"{base_url}.onnx", model_path) and success
    if not config_path.exists():
        success = download_file(f"{base_url}.onnx.json", config_path) and success

    if success and model_path.exists() and config_path.exists():
        return model_path
    
    logger.error(f"Could not acquire Piper voice '{voice_name}'.")
    return None
