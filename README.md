# VibeListen 🎧

**VibeListen** is an open‑source podcast/audio manager that automatically syncs your bookmarks, generates spoken summaries using pluggable TTS engines, and serves a sleek static web UI.

---

## 📦 Project Structure
```
VibeListen/
├─ backend/               # FastAPI server, worker, database, TTS abstraction
│   ├─ main.py            # FastAPI entry point (routes, middleware, CORS)
│   ├─ config.py          # Centralized configuration & env validation
│   ├─ auth.py            # Security utilities (Fernet crypto, API key, CSRF, SSRF)
│   ├─ database.py        # SQLModel SQLite DB wrapper (WAL mode, migrations)
│   ├─ schemas.py         # Settings validation (allowlist + length limits)
│   ├─ syncer.py          # Raindrop.io & Instapaper sync adapters
│   ├─ parser.py          # Article content extraction (readability-lxml)
│   ├─ rss_generator.py   # RSS 2.0 feed builder (xml.etree.ElementTree)
│   ├─ tts.py             # TTS engine dispatcher
│   ├─ tts_engines/       # Pluggable TTS engines (edge, piper, pocket)
│   └─ worker.py          # Background bookmark processing worker
├─ frontend/              # Static HTML/CSS/JS served by FastAPI
│   ├─ index.html         # Dashboard with glassmorphism UI
│   ├─ app.js             # State management, API calls, DOM diffing
│   └─ styles.css         # Premium dark-mode stylesheet
├─ data/                  # Runtime data
│   ├─ audio/             # Generated audio files (.mp3, .wav)
│   ├─ audio_cache/       # Transcoded MP3 cache for podcast feeds
│   ├─ db.sqlite          # SQLite database (WAL mode)
│   └─ models/            # Local TTS model files
├─ tests/                 # Pytest suite (async tests for API & worker)
├─ setup.py              # Setup wizard: bootstrap .env, install deps, diagnostics
├─ install.sh            # Unix one-command installer (creates .venv, runs setup.py)
├─ Dockerfile            # Multi-stage Docker image (amd64 + arm64)
├─ docker-compose.yml    # Single-command Docker deployment
├─ docker-entrypoint.sh  # Docker auto-bootstrap (creates .env on first start)
├─ .dockerignore         # Docker build context exclusions
├─ .env.example          # Example environment configuration
├─ start.py              # Launcher (server + worker in one command)
├─ AGENTS.md             # Developer onboarding & workflow guide
├─ PATCH_NOTES.md        # Release notes
├─ PRD.md                # Product requirements document
└─ README.md              # **This file**
```

---

## 🛠️ Setup & Installation

Choose your pathway:

### Option A — Local (Linux / macOS)
```bash
./install.sh                     # interactive setup (creates .venv, installs deps)
python start.py                  # start server + worker
```
- `./install.sh --engine=piper --quiet` for non-interactive setup
- `python start.py --port 8001` for a custom port
- `python start.py --setup` to re-run the setup wizard
- **Dependencies**: `ffmpeg` is required for audio transcoding.
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Arch: `sudo pacman -S ffmpeg`

### Option B — Docker
```bash
docker compose up -d --build     # builds and starts in background
```
- Container auto-generates `.env` with secure keys on first start
- Data persists in `./data/` (database, audio, models)
- Build a smaller image: `docker compose build --build-arg TTS_PROFILE=edge`

---

## 🚀 Running the application (development)
```bash
# Start both FastAPI server and background worker (development mode)
python start.py                    # default port 8000
python start.py --port 8001        # custom port
PORT=8001 python start.py          # or via PORT env var
```
*The server will be reachable at `http://localhost:8000` (or the configured port) and the static UI is served from the same origin.*

If you only need the API:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
If the default port is occupied, use an alternative (e.g. `--port 8001`).

---

## 🧪 Testing
```bash
python -m pytest          # runs all async tests
python -m pytest tests/test_tts_engines/  # only TTS engine tests
```
Tests cover the FastAPI routes, the background worker logic, and each TTS engine implementation.

---

## 🏗️ Architecture Overview
- **FastAPI backend** (`backend/main.py`) exposes a REST API and serves the static files from `/frontend`.
- **Background worker** (`backend/worker.py`) continuously processes queued bookmarks from Raindrop.io and/or Instapaper. Uses adaptive polling (idle backoff 2s → 30s).
- **Security layer** (`backend/auth.py` + `backend/schemas.py`):
  - API key authentication via `X-API-Key` header (matches `SECRET_KEY`).
  - CSRF protection via `X-Requested-By: VibeListen` header on POST requests.
  - Fernet encryption for credential storage at rest (uses separate `ENCRYPTION_KEY`).
  - SSRF prevention with DNS rebinding protection (single-resolution pattern with `Host` header override).
  - Rate limiting via `slowapi` on all mutating endpoints.
  - Settings validation via allowlist (`backend/schemas.py`) enforcing key names and length limits.
  - Path traversal prevention via `sanitize_filename()` + resolved path containment checks.
- **Database** (`backend/database.py`) uses **SQLite** via **SQLModel** with WAL mode and `busy_timeout=5000` for concurrent read/write performance. Index on `Bookmark.status`.
- **TTS Engine abstraction** (`backend/tts.py` + `backend/tts_engines/`):
  - `edge_engine.py` – Microsoft Edge cloud TTS (default). Outputs `.mp3`. Uses single `edge_tts.Communicate` call.
  - `piper_engine.py` – Local ONNX‑based Piper TTS. Thread-safe voice loading with double-checked locking. Async WAV writes via `aiofiles`. Outputs `.wav`.
  - `pocket_engine.py` – Kyutai Labs Pocket TTS (CALM) using `moshi` TTSModel (1.6B params). Outputs `.wav` at 24000 Hz. Supports "default" voice and "cloned" voice (uploaded 5s 24 kHz mono reference WAV). Inference offloaded via `asyncio.to_thread`. GPU (CUDA) when available.
- **Transcoding pipeline** — WAV files from Piper/Pocket are transcoded to MP3 by the background worker via `ffmpeg`. Transcoded MP3s are cached in `/data/audio_cache/` and served through the `/rss-audio/` endpoint (never spawned on-demand, preventing transcoding DoS).
- **Data storage** (`/data`):
  - `audio/` – generated podcast audio files (`.mp3` from Edge, `.wav` from Piper/Pocket).
  - `audio_cache/` – transcoded MP3 copies for podcast feed compatibility.
  - `db.sqlite` – SQLite DB (WAL mode).
  - `models/` – local TTS model files (Piper voices, Pocket TTS model).

---

## 🌍 Environment Variables (`.env`)
| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | API authentication key (injected into frontend HTML). Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ENCRYPTION_KEY` | **Yes** | Fernet encryption key for credential storage at rest (never client-exposed). Generate with same method as `SECRET_KEY` |
| `RAINDROP_TOKEN` | Optional* | Token for Raindrop.io integration (can also be set via Settings UI) |
| `BASE_URL` | No | Public URL for generated podcast feeds (default `http://localhost:8000`) |
| `TTS_ENGINE` | No | Selected TTS backend — `edge` (default), `piper`, `pocket` |
| `DEFAULT_VOICE` | No | Voice identifier for the chosen engine (default `en-US-GuyNeural`) |
| `SQLITE_DB_PATH` | No | Path to SQLite DB (default `/data/db.sqlite`) |
| `AUDIO_DIR` | No | Directory for generated audio files (default `/data/audio`) |
| `AUDIO_CACHE_DIR` | No | Directory for transcoded MP3 cache (default `/data/audio_cache`) |
| `MODELS_DIR` | No | Directory for local TTS models (default `/data/models`) |
| `REFERENCE_WAV_PATH` | No | Path to reference WAV for Pocket TTS voice cloning (set via UI upload) |

*Credentials can be configured via the Settings UI (stored encrypted in the database) or set via `.env`. Database-stored values take precedence.

---

## 🤝 Contributing
1. Fork the repository and create a feature branch.
2. Follow the **Development Workflow** from `AGENTS.md`:
   - Modify `/backend` or `/frontend`
   - Run `python -m pytest` locally
   - Start services with `python start.py`
3. Open a Pull Request targeting the `v0.6` branch (or the current development branch).  
   - Ensure CI passes and the FastAPI server runs on the CI environment.
   - Update documentation as needed.

### Security Notes
All API contributions must respect the security model:
- New endpoints should use `require_api_key` and (if mutating) `require_csrf_header` dependencies.
- Any user-controlled string rendered in HTML must be escaped via `escapeHTML()`.
- External URLs fetched by the parser are validated through `_validate_url()` (SSRF protection).
- Secrets/tokens stored in the database are automatically encrypted via `encrypt_secret()`.

---

## 📈 Roadmap
- **Completed** (v0.6):
  - API key authentication + CSRF protection + rate limiting.
  - Credential encryption at rest (Fernet).
  - SSRF/DNS rebinding protection with single-resolution pattern.
  - Settings validation (allowlist + length limits).
  - WAL mode + `busy_timeout` for SQLite concurrent access.
  - N+1 query elimination in sync loop.
  - Bulk settings API (single request).
  - Adaptive worker polling with idle backoff.
  - Instapaper OAuth 1.0a integration.
  - Premium glassmorphism UI dashboard with speech & sync settings modals.
  - Inline audio player with speed controls.
  - WAV-to-MP3 transcoding for podcast app compatibility.
  - Settings stored encrypted in database (secrets redacted in API responses).
  - Targeted DOM updates with card map diffing.
- **Future milestones**:
  - Add Docker and Helm deployment scripts.
  - Expand TTS engine support (e.g., Coqui TTS, Mozilla TTS).
  - Introduce CI/CD pipelines with automated testing and publishing.
  - Provide a mobile-friendly progressive web app (PWA) UI.
  - Implement multi‑user support and OAuth authentication.

## 📊 Current State of Development
- **v0.6** includes:
  - Comprehensive security hardening (auth, CSRF, SSRF, rate limiting, encryption, XSS prevention).
  - Pluggable TTS engine system with lazy loading (Edge, Piper, Pocket).
  - Standalone background worker with adaptive polling and ffmpeg transcoding.
  - Full Raindrop.io and Instapaper integration with encrypted credential storage.
  - Premium glassmorphism frontend dashboard with settings management.
  - Comprehensive pytest suite covering API, worker, and TTS engines.
  - SQLite WAL mode with optimized query patterns.
- Ongoing work:
  - Containerization (Docker).
  - CI/CD pipeline setup.
  - Additional TTS engine support.

---

## 📜 License
This project is licensed under the **MIT License** – see `LICENSE` for details.

---

*Happy coding! 🎉*
