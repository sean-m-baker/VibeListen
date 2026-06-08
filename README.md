# VibeListen 🎧

**VibeListen** is an open‑source podcast/audio manager that automatically syncs your bookmarks, generates spoken summaries using pluggable TTS engines, and serves a sleek static web UI.

---

## 📦 Project Structure
```
VibeListen/
├─ backend/               # FastAPI server, worker, database, TTS abstraction
│   ├─ main.py            # FastAPI entry point
│   ├─ worker.py          # Background bookmark sync worker
│   ├─ database.py        # SQLModel SQLite DB wrapper
│   └─ tts_engines/       # Pluggable TTS engines (edge, piper, pocket)
├─ frontend/              # Static HTML/CSS/JS served by FastAPI
├─ data/                  # Runtime data – audio files, SQLite DB, TTS models
├─ tests/                  # Pytest suite (async tests for API & worker)
├─ .env.example          # Example environment configuration
└─ README.md               # **This file**
```

---

## 🛠️ Setup & Installation
1. **Clone the repo**
   ```bash
   git clone https://github.com/yourorg/VibeListen.git
   cd VibeListen
   ```
2. **Create a Python virtual environment** (recommended, Python 3.13+)
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt           # core deps
   pip install -r requirements-local.txt     # all local TTS engines (Piper + Pocket)
   ```
   > Install engines individually for a lighter footprint:
   > - `pip install -r requirements-piper.txt`   — Piper (ONNX‑based, ~50 MB)
   > - `pip install -r requirements-pocket.txt`  — Pocket (PyTorch‑based, ~3 GB on first use, GPU recommended)
4. **Configure environment variables**
   - Copy the example file:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and set the required values (see the **Environment** section).

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
- **Background worker** (`backend/worker.py`) continuously syncs bookmarks from Raindrop.io and/or Instapaper using the `syncer.py` adapter.
- **Database** (`backend/database.py`) uses **SQLite** via **SQLModel** (`SQLITE_DB_PATH` from `.env`).
- **TTS Engine abstraction** (`backend/tts.py` + `backend/tts_engines/`):
  - `edge_engine.py` – Microsoft Edge cloud TTS (default). Outputs `.mp3`.
  - `piper_engine.py` – Local ONNX‑based Piper TTS. Splits long text into 2000‑character chunks at word boundaries. Uses `synthesize_wav()` (piper‑tts v1.4.2). Models auto‑downloaded via `download_voice()`. Outputs `.wav`.
  - `pocket_engine.py` – Kyutai Labs Pocket TTS (CALM) using `moshi` TTSModel (1.6B params). Outputs `.wav` at 24000 Hz. Supports "default" voice (first available from `kyutai/tts-voices` HF repo) and "cloned" voice (uploaded 5s 24 kHz mono reference WAV). First use downloads ~3 GB model from HuggingFace. Automatically uses GPU (CUDA) when available.
- **Data storage** (`/data`):
  - `audio/` – generated podcast audio files.
  - `db.sqlite` – SQLite DB.
  - `models/` – optional local TTS model files.

---

## 🌍 Environment Variables (`.env`)
| Variable | Description |
|---|---|
| `RAINDROP_TOKEN` | Required token for Raindrop.io integration |
| `BASE_URL` | Public URL for generated podcast feeds (default `http://localhost:8000`) |
| `TTS_ENGINE` | Selected TTS backend (`edge`, `piper`, `pocket`) |
| `DEFAULT_VOICE` | Voice identifier for the chosen engine: Edge voices like `en-US-AvaNeural`; Piper voices like `en_US-lessac-medium` (auto‑downloaded on first use); Pocket voices use `default` (auto‑select first available) or `cloned` (reference WAV) |
| `SQLITE_DB_PATH` | Path to SQLite DB (default `/data/db.sqlite`) |
| `AUDIO_DIR` | Directory for generated audio files (default `/data/audio`) |
| `MODELS_DIR` | Directory for local TTS models (default `/data/models`) |
| `REFERENCE_WAV_PATH` | Path to reference WAV for Pocket TTS voice cloning (set automatically via UI upload at `/api/tts/reference`) |

---

## 🤝 Contributing
1. Fork the repository and create a feature branch.
2. Follow the **Development Workflow** from `AGENTS.md`:
   - Modify `/backend` or `/frontend`
   - Run `python -m pytest` locally
   - Start services with `python start.py`
3. Open a Pull Request targeting the `v0.3` branch (or the current development branch).  
   - Ensure CI passes and the FastAPI server runs on the CI environment.
   - Update documentation as needed.

---

## 📈 Roadmap
- **Future milestones**:
  - Add Docker and Helm deployment scripts.
  - Expand TTS engine support (e.g., Coqui TTS, Mozilla TTS).
  - Introduce CI/CD pipelines with automated testing and publishing.
  - Provide a mobile-friendly progressive web app (PWA) UI.
  - Implement multi‑user support and OAuth authentication.

## 📊 Current State of Development
- **v0.3 branch** includes:
  - Pluggable TTS engine system with lazy loading (Edge, Piper, Pocket).
  - Standalone background worker for asynchronous bookmark syncing.
  - Comprehensive pytest suite covering API, worker, and TTS engines.
  - Improved configuration via `.env` and database‑backed settings.
  - Static frontend served by FastAPI with a clean UI.
- Ongoing work:
  - Refining error handling and logging.
  - Enhancing documentation and developer onboarding.

---

## 📜 License
This project is licensed under the **MIT License** – see `LICENSE` for details.

---

*Happy coding! 🎉*
