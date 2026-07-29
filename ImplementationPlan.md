# Streamlined Installation & Setup Implementation Plan

This implementation plan details how to transform VibeListen's installation experience from a multi-step manual process into a streamlined, single-command setup for both local Python development environments and Docker container deployments.

---

## 🎯 Objectives & Key Design Decisions

Based on our interactive design review, the streamlined installation system will focus on:

1. **Dual Installation Pathways**:
   - **Local Python Environment**: One-command interactive setup script (`install.sh` / `python setup.py` / `python start.py --setup`) for bare-metal & virtualenv users.
   - **Docker Containerization**: Standardized `Dockerfile` + `docker-compose.yml` for single-command (`docker compose up -d`) container deployment.
2. **Automated Secret Key & Configuration Bootstrap**:
   - Automatic generation of cryptographically secure Fernet keys (`SECRET_KEY` and `ENCRYPTION_KEY`) using **stdlib `os.urandom` + `base64`** (avoids chicken-and-egg dependency on `cryptography`).
   - Keys validated against `cryptography.fernet.Fernet` after core deps install.
   - Automatic creation and population of `.env` from `.env.example` if missing.
   - Automatic creation of runtime directories (`/data/audio`, `/data/audio_cache`, `/data/models`, `/data/db.sqlite`).
3. **Interactive TTS Engine Selection & Modular Dependency Installation**:
   - Interactive prompt asking the user for their TTS preference: `edge` (cloud/lightweight), `piper` (local ONNX, ~50MB), `pocket` (local CALM/Moshi, PyTorch), or `all`.
   - Non-interactive CLI flag support (e.g., `./install.sh --engine=edge|piper|pocket|all` or `./install.sh --quiet`).
   - Selective pip dependency installation (`requirements.txt` + engine-specific requirements files).
   - **Graceful pip failure handling**: failed engine installs fall back to `edge` with clear diagnostics.
4. **Informative Pre-flight System Diagnostics**:
   - Automatic check for Python 3.10+ / 3.13.
   - Automatic check for `ffmpeg` on system `PATH` (printing OS-specific commands like `sudo apt install ffmpeg` or `brew install ffmpeg` if missing).
   - Optional GPU/CUDA detection when Pocket TTS is selected.
5. **Auto-Bootstrapping Launcher (`start.py`)**:
   - `python start.py` imports `setup` module and calls `ensure_env_configured(quiet=True)` to auto-generate keys/dirs before starting services.
   - Supports `--setup` flag for running or re-running the interactive configuration wizard.
6. **Docker**: All TTS engines installed by default; `TTS_PROFILE` build arg for smaller images; health check included; `.env` auto-bootstrapped on container start.

---

## 🏗️ Proposed Changes

---

### 1. Installation Scripts & Utilities

#### [NEW] [install.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/install.sh)
- Unix shell entrypoint script for one-command local setup.
- Checks for `python3`, creates virtualenv at `.venv` if missing, activates it, and delegates to `python setup.py`.
- Supports CLI flags: `--engine=<type>`, `--quiet`, `--skip-deps`, `--help`.

#### [NEW] [setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py)
- **Dual-mode**: importable module + standalone CLI script.
- Exported functions: `ensure_env_configured()`, `generate_fernet_key()`, `ensure_data_dirs()`, `check_ffmpeg()`, `check_python_version()`, `install_tts_deps()`.
- **Diagnostics**: Checks Python version, virtualenv status, `ffmpeg` binary availability (`shutil.which("ffmpeg")`), CUDA/torch availability.
- **Environment Configuration**: Copies `.env.example` -> `.env`, generates `SECRET_KEY` and `ENCRYPTION_KEY` using **stdlib `os.urandom` + `base64`**, prompts optionally for `BASE_URL` or `RAINDROP_TOKEN`.
- **Directory Bootstrap**: Ensures `/data`, `/data/audio`, `/data/audio_cache`, `/data/models` exist with `0o755` permissions.
- **TTS Engine Setup**: Prompts for TTS engine profile (`edge`, `piper`, `pocket`, `all`) and executes `pip install` targeting the correct `requirements-*.txt`. Uses `subprocess.run(check=False)` — on failure, falls back to `edge` with clear error message.

---

### 2. Launcher Hardening & Auto-Bootstrapping

#### [MODIFY] [start.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/start.py)
- Add auto-bootstrap check on launch:
  - `from setup import ensure_env_configured, ensure_data_dirs` (module, not subprocess).
  - Calls `ensure_env_configured(quiet=True)` — generates `.env` and keys if missing.
  - Calls `ensure_data_dirs()` — creates `/data` subdirectories if missing.
  - Checks if `ffmpeg` is installed; prints warning if missing when local TTS engines are configured.
- Add `--setup` CLI flag to trigger `setup.py` interactively.

#### [MODIFY] [start.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/start.sh)
- Check if `.venv` exists; if missing, print message suggesting `./install.sh` and exit with code 1.

---

### 3. Containerization (Docker)

#### [NEW] [Dockerfile](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/Dockerfile)
- Multi-stage Docker image based on `python:3.11-slim` (supports `linux/amd64` + `linux/arm64`).
- Installs system dependencies: `ffmpeg`, `curl`, build tools.
- **TTS strategy**: Install all TTS engines by default (`requirements-local.txt`).
- `TTS_PROFILE` build arg (`edge`, `piper`, `pocket`, `all`) for smaller images.
- Copies application codebase and exposes port 8000.
- Entrypoint runs `.env` bootstrap then `python start.py`:
  ```dockerfile
  ENTRYPOINT ["sh", "-c", "python -c 'from setup import ensure_env_configured; ensure_env_configured(quiet=True)' && exec python start.py"]
  ```

#### [NEW] [.dockerignore](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/.dockerignore)
- Excludes `.venv`, `.git`, `.pytest_cache`, `__pycache__`, `data/*.sqlite`, `data/audio/*` from container context.

#### [NEW] [docker-compose.yml](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/docker-compose.yml)
- Defines `vibelisten` service with port mapping `8000:8000`.
- Mounts host `./data` directory to `/app/data` for SQLite DB, audio, and model persistence.
- Loads environment variables from `.env` file (auto-bootstrapped on container start).
- Adds health check: `curl -f http://localhost:8000/` every 30s.
- Restart policy: `unless-stopped`.

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
2. **Setup Script Tests** (`tests/test_setup.py`) — new test file:
   - `test_generate_fernet_key_valid`: valid 44-char base64 string accepted by `Fernet(key)`.
   - `test_ensure_data_dirs_creates_directories`: creates expected dirs in `tmp_path`.
   - `test_ensure_env_configured_quiet`: copies `.env.example`, injects keys, preserves existing on re-run.
   - `test_cli_quiet`: `python setup.py --quiet --engine=piper` via subprocess in isolated temp env.
   - `test_tts_engine_edge_installs_core_only`: mocked pip, verify only `requirements.txt` called.
   - `test_tts_install_failure_fallback`: mocked pip failure, verify fallback to edge.
3. **Launcher Tests** (`tests/test_start.py`) — new test file:
   - Test `start.py` auto-bootstraps `.env` when missing (mocked subprocess).
   - Test `start.py --setup` invokes setup wizard.
   - Test `start.py` with existing `.env` does not overwrite.

### Manual Verification
1. **Fresh Clone Local Setup**:
   - Test `./install.sh` on a clean environment without pre-existing `.env` or `.venv`.
   - Verify interactive wizard correctly prompts for TTS engine choices and installs requirements.
   - Run `python start.py` and verify FastAPI server loads at `http://localhost:8000`.
2. **Docker Deployment Test**:
   - Run `docker compose up -d --build`.
   - Verify container starts cleanly, health checks succeed, and web interface is accessible at `http://localhost:8000`.
   - Verify persistence by creating a test setting, restarting container, and ensuring data remains in `./data`.
3. **Pip failure scenario**:
   - Mock a network failure during `pip install -r requirements-pocket.txt`.
   - Verify setup prints clear error and falls back to `edge` engine.
   - Verify `TTS_ENGINE=edge` and `TTS_ENGINE_FAILED=pocket` in `.env`.
