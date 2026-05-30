# VibeListen Agent Guidance

## Project Structure
- **Backend**: Python/FastAPI server (`/backend`) handling API, TTS, syncing
- **Frontend**: Static web interface (`/frontend`) served by backend
- **Tests**: Pytest suite (`/tests/`) for backend components
- **Data**: Storage directory (`/data/`) for audio files and database

## Key Commands
- **Start server & worker**: `python start.py` (runs both processes)
- **Start server only**: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- **Start worker only**: `python backend/worker.py`
- **Run tests**: `python -m pytest` (from project root)
- **Install dependencies**: `pip install -r requirements.txt`
- **Install local TTS engines**: `pip install -r requirements-local.txt`

## Development Workflow
1. Modify code in `/backend` or `/frontend`
2. Test changes: `python -m pytest`
3. Start services: `python start.py` (or separately: server + worker)
4. Access frontend at http://localhost:8000

## Architecture Notes
- **Entry points**: 
  - Backend API: `backend/main.py` (FastAPI app)
  - Background worker: `backend/worker.py` (processing loop)
  - Launcher: `start.py` (starts both server and worker)
- **Database**: SQLite via SQLModel (`backend/database.py`)
- **TTS Engines**: Pluggable system in `/backend/tts_engines/` (edge, piper, pocket)
- **Services**: Integration adapters in backend/ (syncer.py, pocket.py, etc.)

## Testing Conventions
- Tests use pytest with asyncio support
- Mock external APIs where appropriate
- Test files mirror module structure (test_*.py)
- Run specific TTS engine tests: `python -m pytest tests/test_tts_engines/`

## Environment & Configuration
- Environment variables loaded from `.env` file at project root
- Copy `.env.example` to `.env` and configure:
  - `RAINDROP_TOKEN` (required for Raindrop.io integration)
  - `BASE_URL` (public URL for podcast feeds, default: http://localhost:8000)
  - `TTS_ENGINE` (default: "edge", options: edge, piper, pocket)
  - `DEFAULT_VOICE` (TTS voice, e.g., en-US-AvaNeural)
  - `SQLITE_DB_PATH` (default: /data/db.sqlite)
  - `AUDIO_DIR` (default: /data/audio)
  - `MODELS_DIR` (default: /data/models, for TTS models)
  - `REFERENCE_WAV_PATH` (for voice cloning reference audio)
- PYTHONPATH automatically set to project root by start.py (required for imports)
- Database uses SQLite with SQLModel (check_same_thread=False required for FastAPI)

## Important Quirks
- Backend serves frontend static files at root URL
- Worker processes bookmarks asynchronously via background loop
- Audio files stored in `/data/audio/`
- Database stored in `/data/db.sqlite` (or path set by SQLITE_DB_PATH env var)
- TTS engines may require additional system dependencies:
  - Piper: Needs piper phoneme files
  - Pocket TTS: Requires model download on first use