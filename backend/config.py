import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (parent of backend/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file at the project root
load_dotenv(BASE_DIR / ".env")

# Security: required key for API auth + credential encryption
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )

# API Keys & Network settings
RAINDROP_TOKEN = os.getenv("RAINDROP_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# Speech & TTS Engine Settings
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge").strip().lower()
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "en-US-GuyNeural")

# Storage Directories & Files
DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", DATA_DIR / "db.sqlite"))
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", DATA_DIR / "audio"))
MODELS_DIR = Path(os.getenv("MODELS_DIR", DATA_DIR / "models"))

# Voice Cloning reference path (global 5-second WAV for Pocket TTS / others)
REFERENCE_WAV_PATH = Path(os.getenv("REFERENCE_WAV_PATH", MODELS_DIR / "reference.wav"))

# Transcoded audio cache (MP3 copies of WAV files for mobile RSS)
AUDIO_CACHE_DIR = Path(os.getenv("AUDIO_CACHE_DIR", DATA_DIR / "audio_cache"))

# Ensure dynamic storage folders exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
