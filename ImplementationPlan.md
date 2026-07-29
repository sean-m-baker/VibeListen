# Streamlined Installation & Setup Implementation Plan

This implementation plan details how to transform VibeListen's installation experience from a multi-step manual process into a streamlined, single-command setup for both local Python development environments and Docker container deployments.

---

## 🎯 Objectives & Key Design Decisions

Based on our interactive design review, the streamlined installation system will focus on:

1. **Dual Installation Pathways**:
   - **Local Python Environment**: One-command interactive setup script (`install.sh` / `python setup.py` / `python start.py --setup`) for bare-metal & virtualenv users.
   - **Docker Containerization**: Standardized `Dockerfile` + `docker-compose.yml` for single-command (`docker compose up -d`) container deployment.
2. **Automated Secret Key & Configuration Bootstrap**:
   - Automatic generation of cryptographically secure Fernet keys (`SECRET_KEY` and `ENCRYPTION_KEY`) using `cryptography`.
   - Automatic creation and population of `.env` from `.env.example` if missing.
   - Automatic creation of runtime directories (`/data/audio`, `/data/audio_cache`, `/data/models`, `/data/db.sqlite`).
3. **Interactive TTS Engine Selection & Modular Dependency Installation**:
   - Interactive prompt asking the user for their TTS preference: `edge` (cloud/lightweight), `piper` (local ONNX, ~50MB), `pocket` (local CALM/Moshi, PyTorch), or `all`.
   - Non-interactive CLI flag support (e.g., `./install.sh --engine=edge|piper|pocket|all` or `./install.sh --quiet`).
   - Selective pip dependency installation (`requirements.txt` + engine-specific requirements files).
4. **Informative Pre-flight System Diagnostics**:
   - Automatic check for Python 3.10+ / 3.13.
   - Automatic check for `ffmpeg` on system `PATH` (printing OS-specific commands like `sudo apt install ffmpeg` or `brew install ffmpeg` if missing).
   - Optional GPU/CUDA detection when Pocket TTS is selected.
5. **Auto-Bootstrapping Launcher (`start.py`)**:
   - `python start.py` auto-detects missing `.env` or data directories on a fresh clone and generates keys/dirs automatically before starting services.
   - Supports `--setup` flag for running or re-running the interactive configuration wizard.

---

## 🏗️ Proposed Changes

---

### 1. Installation Scripts & Utilities

#### [NEW] [install.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/install.sh)
- Unix shell entrypoint script for one-command local setup.
- Checks for `python3`, creates virtualenv at `.venv` if missing, activates it, and delegates to `python setup.py`.
- Supports CLI flags: `--engine=<type>`, `--quiet`, `--skip-deps`, `--help`.

#### [NEW] [setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py)
- Python setup utility script handling cross-platform setup logic:
  - **Diagnostics**: Checks Python version, virtualenv status, `ffmpeg` binary availability (`shutil.which("ffmpeg")`), CUDA/torch availability.
  - **Environment Configuration**: Copies `.env.example` -> `.env`, generates `SECRET_KEY` and `ENCRYPTION_KEY` using `cryptography.fernet.Fernet`, prompts optionally for `BASE_URL` or `RAINDROP_TOKEN`.
  - **Directory Bootstrap**: Ensures `/data`, `/data/audio`, `/data/audio_cache`, `/data/models` exist with proper permissions.
  - **TTS Engine Setup**: Prompts for TTS engine profile (`edge`, `piper`, `pocket`, `all`) and executes `pip install` targeting the correct `requirements-*.txt`.

---

### 2. Launcher Hardening & Auto-Bootstrapping

#### [MODIFY] [start.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/start.py)
- Add auto-bootstrap check on launch:
  - Checks if `.env` exists; if not, triggers secret key generation & `.env` creation automatically.
  - Checks if `/data` subdirectories exist; creates them if missing.
  - Checks if `ffmpeg` is installed; prints warning if missing when local TTS engines are configured.
- Add `--setup` CLI flag to trigger `setup.py` interactively.

#### [MODIFY] [start.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/start.sh)
- Check if `.venv` exists; if missing, suggest running `./install.sh` or auto-triggering `./install.sh --quiet`.

---

### 3. Containerization (Docker)

#### [NEW] [Dockerfile](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/Dockerfile)
- Multi-stage Docker image based on `python:3.11-slim` or `python:3.13-slim`.
- Installs system dependencies: `ffmpeg`, `curl`, build tools.
- Installs Python dependencies (`requirements.txt` + `requirements-local.txt` or build arg controlled).
- Copies application codebase and exposes port 8000.
- Sets entrypoint to `python start.py`.

#### [NEW] [.dockerignore](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/.dockerignore)
- Excludes `.venv`, `.git`, `.pytest_cache`, `__pycache__`, `data/*.sqlite`, `data/audio/*` from container context.

#### [NEW] [docker-compose.yml](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/docker-compose.yml)
- Defines `vibelisten` service with port mapping `8000:8000`.
- Mounts host `./data` directory to `/app/data` for SQLite DB, audio, and model persistence.
- Loads environment variables from `.env` file (with auto-key generation script if run via docker helper).

---

### 4. Documentation & Onboarding Updates

#### [MODIFY] [README.md](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/README.md)
- Simplify **Setup & Installation** section:
  - **Option A (Quick Local Setup)**: Run `./install.sh` (or `python setup.py`), then `python start.py`.
  - **Option B (Docker)**: Run `docker compose up -d`.
- Add **Troubleshooting & System Dependencies** section explaining `ffmpeg` installation per platform.

#### [MODIFY] [AGENTS.md](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/AGENTS.md)
- Update **Key Commands** and **Development Workflow** with `./install.sh`, `python setup.py`, and Docker commands.

---

## 🧪 Verification Plan

### Automated Verification
1. **Pytest Integration**: Ensure all existing tests pass after `setup.py` / `start.py` modifications:
   ```bash
   python -m pytest
   ```
2. **Setup Script Dry-Run / Non-Interactive Test**:
   - Run `python setup.py --quiet --engine=edge` in a clean temporary workspace or environment.
   - Verify `.env` is created with valid `SECRET_KEY` and `ENCRYPTION_KEY` Fernet tokens.
   - Verify `/data/audio`, `/data/audio_cache`, `/data/models` directories are created.

### Manual Verification
1. **Fresh Clone Local Setup**:
   - Test `./install.sh` on a clean environment without pre-existing `.env` or `.venv`.
   - Verify interactive wizard correctly prompts for TTS engine choices and installs requirements.
   - Run `python start.py` and verify FastAPI server loads at `http://localhost:8000`.
2. **Docker Deployment Test**:
   - Run `docker compose up -d --build`.
   - Verify container starts cleanly, health checks succeed, and web interface is accessible at `http://localhost:8000`.
   - Verify persistence by creating a test setting, restarting container, and ensuring data remains in `./data`.
