# Installation Streamlining: Epics, Features & User Stories

This document breaks down the **Streamlined Installation & Setup Implementation Plan** into Agile **Features (Epics)**, **User Stories**, **Tasks**, and **Acceptance Criteria**. Each story is sized for incremental implementation and independent verification.

---

## 📋 Feature 1: Automated Local Setup Wizard & Pre-Flight Diagnostics (`setup.py` & `install.sh`)

### 👤 User Story 1.1: Automated `.env` Bootstrap & Secret Key Generation
> **As a** new developer or user cloning VibeListen,  
> **I want** the setup tool to automatically create `.env` and generate cryptographically secure secret keys (`SECRET_KEY` and `ENCRYPTION_KEY`),  
> **So that** I don't have to manually copy `.env.example`, run Python one-liners, and copy-paste Fernet keys into configuration files.

#### 🛠️ Tasks
- [ ] **Task 1.1.1a**: Implement `generate_fernet_key()` using stdlib only (`os.urandom` + `base64.urlsafe_b64encode`) to avoid requiring `cryptography` pre-installation.
  - `def generate_fernet_key() -> str: return base64.urlsafe_b64encode(os.urandom(32)).decode()`
  - Check if `.env` exists; if missing, copy `.env.example` to `.env`.
  - Safely inject generated keys into `.env` without overwriting other existing values.
- [ ] **Task 1.1.1b**: After `pip install -r requirements.txt` completes, validate generated keys via `cryptography.fernet.Fernet(key)` — fail with a clear error if invalid.
- [ ] **Task 1.1.1c**: Structure `setup.py` as a dual-mode module with these exported functions (importable by `start.py` and invocable via CLI):
  - `ensure_env_configured(interactive: bool = False, engine: str | None = None, quiet: bool = False) -> dict` — returns `{"env_created": bool, "dirs_created": list[str], "engine": str}`.
  - `generate_fernet_key() -> str`
  - `ensure_data_dirs() -> list[Path]`
  - `check_ffmpeg() -> bool`
  - `check_python_version() -> bool`
  - `install_tts_deps(engine: str, quiet: bool = False) -> bool`
  - CLI entry: `if __name__ == "__main__":` parses args and calls the above.
- [ ] **Task 1.1.2**: Implement runtime directory creation logic in `setup.py`:
  - Ensure `/data`, `/data/audio`, `/data/audio_cache`, and `/data/models` are created with `0o755` permissions.
- [ ] **Task 1.1.3**: Add `test_setup.py` with unit/integration tests for `setup.py` bootstrap:
  - `test_generate_fernet_key_valid`: generated key is 44-char base64 string accepted by `Fernet(key)`.
  - `test_ensure_data_dirs_creates_directories`: creates expected dirs in temp dir via `tmp_path`.
  - `test_ensure_env_configured_quiet`: copies `.env.example`, injects keys, preserves existing on re-run.
  - `test_cli_quiet`: `python setup.py --quiet --engine=piper` via subprocess in isolated temp env.
- [ ] **Task 1.1.4**: In interactive mode, prompt user for `RAINDROP_TOKEN` (optional — can be set later via Settings UI). Skip in `--quiet` mode.

#### 🎯 Acceptance Criteria
- Running `python setup.py` on a fresh clone automatically generates `.env` with valid 32-byte base64-encoded Fernet strings for `SECRET_KEY` and `ENCRYPTION_KEY`.
- All required `/data` directories are auto-created with `0o755` permissions.
- Existing `.env` files are not overwritten or corrupted if `setup.py` is re-run.
- `start.py` can `from setup import ensure_env_configured` without side effects.
- Keys remain valid after `cryptography` is installed (verified by `Fernet(key)`).

---

### 👤 User Story 1.2: Interactive & Modular TTS Dependency Installation
> **As a** user installing VibeListen locally,  
> **I want** an interactive prompt that lets me choose my desired TTS engine profile (`edge`, `piper`, `pocket`, or `all`),  
> **So that** I only install the Python dependencies I actually need for my hardware and use case.

#### 🛠️ Tasks
- [ ] **Task 1.2.1**: Implement interactive TTS engine selector CLI prompt in `setup.py`:
  - Options: `1) edge (cloud, lightweight - default)`, `2) piper (local ONNX, ~50MB)`, `3) pocket (local CALM/Moshi, PyTorch)`, `4) all (install everything)`.
- [ ] **Task 1.2.2**: Add non-interactive flag support to `setup.py` and `install.sh`:
  - `--engine=<edge|piper|pocket|all>`
  - `--quiet` / `-y` (accept defaults)
- [ ] **Task 1.2.3**: Automate `pip install` execution:
  - Always install base `requirements.txt`.
  - Conditionally run `pip install -r requirements-piper.txt`, `requirements-pocket.txt`, or `requirements-local.txt` based on user selection.
  - Automatically update `TTS_ENGINE` and `DEFAULT_VOICE` in `.env` to match selected engine.
- [ ] **Task 1.2.3a — pip failure handling**:
  - Wrap each `pip install` in `subprocess.run(check=False)`.
  - On failure in interactive mode: print clear error identifying which requirements file failed, ask user to continue or abort.
  - On failure in `--quiet` mode: log the error, set `TTS_ENGINE=edge` as fallback, set `TTS_ENGINE_FAILED=<engine>` in `.env` for diagnostics.
- [ ] **Task 1.2.3b — install summary**:
  - Print structured result table after all installs:
    ```
    ✓ Core dependencies installed
    ✓ Piper TTS dependencies installed
    ✗ Pocket TTS dependencies FAILED. Falling back to edge.
    ```
- [ ] **Task 1.2.4**: Create Unix wrapper script `install.sh`:
  - Auto-detect `python3`, create `.venv` if missing (`python3 -m venv .venv`), activate `.venv`, and call `python setup.py "$@"`.
- [ ] **Task 1.2.5 — test TTS install**:
  - Mock `subprocess.run` to verify correct requirements files are invoked per engine selection.
  - Test `--quiet` skips prompts and uses defaults.
  - Test `--engine=edge` installs only `requirements.txt` (not piper/pocket).
  - Test pip failure handling: mock a pip failure, verify fallback to `edge` in quiet mode.

#### 🎯 Acceptance Criteria
- Running `./install.sh` in interactive mode presents a clean CLI menu and installs only the requested TTS dependencies.
- Running `./install.sh --engine=piper --quiet` installs core + piper requirements in non-interactive mode.
- The `.env` file reflects the chosen engine default after setup completes.
- If Pocket TTS pip install fails, setup completes with `edge` as fallback and a clear error message.

---

### 👤 User Story 1.3: Informative Pre-Flight Diagnostics
> **As a** user installing VibeListen,  
> **I want** the setup script to perform pre-flight system checks (Python version, `ffmpeg` availability, CUDA support),  
> **So that** I am immediately informed of missing system requirements with clear, OS-specific resolution instructions.

#### 🛠️ Tasks
- [ ] **Task 1.3.1**: Implement Python version validation in `setup.py` (enforce Python 3.10+; recommend 3.13+).
- [ ] **Task 1.3.2**: Implement `ffmpeg` binary check using `shutil.which("ffmpeg")`:
  - If missing, print a friendly notice with OS-specific install commands:
    - Ubuntu/Debian: `sudo apt install ffmpeg`
    - macOS: `brew install ffmpeg`
    - Arch: `sudo pacman -S ffmpeg`
- [ ] **Task 1.3.3**: Implement CUDA/GPU availability check (`torch.cuda.is_available()`) if `pocket` engine is selected, warning the user if running PyTorch on CPU-only hardware.

#### 🎯 Acceptance Criteria
- Missing `ffmpeg` prints helpful OS-specific installation instructions without crashing the script.
- Unsupported Python versions trigger a clear error message.
- Diagnostic output clearly indicates system readiness prior to starting the server.

---

## 📋 Feature 2: Auto-Bootstrapping Launcher (`start.py` & `start.sh`)

### 👤 User Story 2.1: First-Run Zero-Config Startup
> **As a** user who runs `python start.py` immediately after cloning,  
> **I want** the launcher to auto-bootstrap missing environment files and directories if they don't exist,  
> **So that** the application starts cleanly without manual configuration.

#### 🛠️ Tasks
- [ ] **Task 2.1.1**: Enhance `start.py` startup sequence:
  - `from setup import ensure_env_configured, ensure_data_dirs`
  - Call `ensure_env_configured(quiet=True)` before launching uvicorn or background worker.
  - Call `ensure_data_dirs()` to create /data subdirectories.
- [ ] **Task 2.1.2**: Add `--setup` CLI flag to `start.py` (`python start.py --setup`) to trigger the interactive `setup.py` wizard directly from the launcher.
- [ ] **Task 2.1.3**: Update `start.sh` — if `.venv` is missing, print a message suggesting `./install.sh` and exit with code 1 (do not auto-create).

#### 🎯 Acceptance Criteria
- Running `python start.py` on a freshly cloned repo without `.env` auto-generates `.env` and `/data` dirs, launching the application smoothly on port 8000.
- Running `python start.py --setup` launches the interactive setup wizard.

### 👤 User Story 2.2: Bootstrapping is Tested
> **As a** developer maintaining `start.py`,  
> **I want** the auto-bootstrap path to have test coverage,  
> **So that** regressions in first-run behavior are caught by CI.

#### 🛠️ Tasks
- [ ] **Task 2.2.1**: Test `start.py` with missing `.env`: mock uvicorn subprocess, verify `ensure_env_configured` creates `.env` before starting server.
- [ ] **Task 2.2.2**: Test `--setup` flag invokes `setup.py` interactive mode (verify subprocess call target).
- [ ] **Task 2.2.3**: Test `start.py` with existing `.env`: verify no overwrite occurs.

#### 🎯 Acceptance Criteria
- Test confirms `.env` is auto-created when missing.
- Test confirms re-running `start.py` with existing `.env` does not overwrite it.

---

## 📋 Feature 3: Docker & Containerized Deployment

### 👤 User Story 3.1: Single-Command Docker Deployment
> **As a** DevOps engineer or home-lab user,  
> **I want** a production-ready `Dockerfile` and `docker-compose.yml`,  
> **So that** I can deploy VibeListen with a single command (`docker compose up -d`).

#### 🛠️ Tasks
- [ ] **Task 3.1.1**: Create multi-stage `Dockerfile`:
  - Base image: `python:3.11-slim`.
  - Install system dependencies (`ffmpeg`, `curl`, build essentials).
  - Copy `requirements.txt` and install pip dependencies.
  - Copy application code.
  - Set entrypoint: `python start.py`.
- [ ] **Task 3.1.1a — Docker TTS strategy**:
  - Default: install ALL TTS engines (`requirements-local.txt`) for maximum runtime flexibility.
  - Add `TTS_PROFILE` build arg (`edge`, `piper`, `pocket`, `all`) for advanced users:
    ```dockerfile
    ARG TTS_PROFILE=all
    COPY requirements*.txt ./
    RUN pip install -r requirements.txt && \
        if [ "$TTS_PROFILE" != "edge" ]; then \
          pip install -r requirements-local.txt; \
        fi
    ```
- [ ] **Task 3.1.2**: Create `.dockerignore` file excluding `.venv`, `__pycache__`, `.pytest_cache`, and local SQLite database files.
- [ ] **Task 3.1.3**: Create `docker-compose.yml`:
  - Service: `vibelisten`
  - Port mapping: `8000:8000`
  - Volume mount: `./data:/app/data`
  - Env file: `.env`
  - Restart policy: `unless-stopped`
- [ ] **Task 3.1.3a — Docker .env bootstrap**:
  - Docker entrypoint runs `python -c "from setup import ensure_env_configured; ensure_env_configured(quiet=True)"` before `python start.py`.
- [ ] **Task 3.1.3b — health check**:
  ```yaml
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/"]
    interval: 30s
    timeout: 10s
    retries: 5
  ```
- [ ] **Task 3.1.3c — multi-platform note**:
  - Verify `python:3.11-slim` supports `linux/amd64` and `linux/arm64`.
  - Document that Pocket TTS (PyTorch) may need platform-specific wheels on ARM.

#### 🎯 Acceptance Criteria
- `docker compose up -d --build` builds the container image cleanly with all TTS engines by default.
- Container starts FastAPI and worker via `start.py`.
- Application is accessible at `http://localhost:8000`.
- Data, database, audio, and models persist across container restarts in `./data`.
- Container health check passes within 30s of startup.
- Building with `--build-arg TTS_PROFILE=edge` produces a smaller image without local TTS deps.

---

## 📋 Feature 4: Documentation Streamlining

### 👤 User Story 4.1: Streamlined Documentation & Quickstart
> **As a** developer or user reading `README.md` and `AGENTS.md`,  
> **I want** clear, updated installation instructions reflecting the new automated setup script and Docker pathways,  
> **So that** onboarding takes under 2 minutes.

#### 🛠️ Tasks
- [ ] **Task 4.1.1**: Update `README.md` Setup & Installation section:
  - **Quickstart (Local)**: `./install.sh` -> `python start.py`
  - **Quickstart (Docker)**: `docker compose up -d`
  - **Troubleshooting**: `ffmpeg` installation guide per OS.
- [ ] **Task 4.1.2**: Update `AGENTS.md` Key Commands and Environment section with `./install.sh`, `python setup.py`, and Docker commands.

#### 🎯 Acceptance Criteria
- `README.md` setup instructions are simplified to 2 main pathways (Local CLI script vs Docker).
- All command examples in docs are verified working.

---

## 🧪 Overall Verification & Definition of Done

1. All User Stories complete with acceptance criteria verified.
2. `python -m pytest` passes 100% (including new `test_setup.py` tests).
3. Fresh local installation via `./install.sh` verified on Linux/macOS.
4. Fresh Docker installation via `docker compose up -d` verified.
5. Fresh clone `python start.py` launches without manual `.env` setup.
6. Pip install failures are handled gracefully without crashing setup.
