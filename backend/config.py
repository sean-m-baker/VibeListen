import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (parent of backend/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file at the project root
load_dotenv(BASE_DIR / ".env")

# API Keys & Network settings
RAINDROP_TOKEN = os.getenv("RAINDROP_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# Speech Settings
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "en-US-GuyNeural")

# Storage Directories & Files
DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", DATA_DIR / "db.sqlite"))
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", DATA_DIR / "audio"))

# Ensure dynamic storage folders exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
