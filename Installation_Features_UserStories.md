# Installation Streamlining: Epics, Features & User Stories

This document breaks down the **Streamlined Installation & Setup Implementation Plan** into Agile **Features (Epics)**, **User Stories**, **Tasks**, and **Acceptance Criteria**. Each story is sized for incremental implementation and independent verification.

---

## 📋 Feature 1: Automated Local Setup Wizard & Pre-Flight Diagnostics (`setup.py` & `install.sh`)

### 👤 User Story 1.1: Automated `.env` Bootstrap & Secret Key Generation
> **As a** new developer or user cloning VibeListen,  
> **I want** the setup tool to automatically create `.env` and generate cryptographically secure secret keys (`SECRET_KEY` and `ENCRYPTION_KEY`),  
> **So that** I don't have to manually copy `.env.example`, run Python one-liners, and copy-paste Fernet keys into configuration files.

#### 🛠️ Tasks
- [ ] **Task 1.1.1**: Create `setup.py` script with environment initializer functions:
  - Check if `.env` exists; if missing, copy `.env.example` to `.env`.
  - Use Python's `cryptography.fernet.Fernet.generate_key()` to generate Fernet tokens for `SECRET_KEY` and `ENCRYPTION_KEY`.
  - Safely inject generated keys into `.env` without overwriting other existing values.
- [ ] **Task 1.1.2**: Implement runtime directory creation logic in `setup.py`:
  - Ensure `/data`, `/data/audio`, `/data/audio_cache`, and `/data/models` are created with standard read/write permissions.
- [ ] **Task 1.1.3**: Add unit/integration test for `setup.py` environment bootstrapping.

#### 🎯 Acceptance Criteria
- Running `python setup.py` on a fresh clone automatically generates `.env` with valid 32-byte base64-encoded Fernet strings for `SECRET_KEY` and `ENCRYPTION_KEY`.
- All required `/data` directories are auto-created.
- Existing `.env` files are not overwritten or corrupted if `setup.py` is re-run.

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
- [ ] **Task 1.2.4**: Create Unix wrapper script `install.sh`:
  - Auto-detect `python3`, create `.venv` if missing (`python3 -m venv .venv`), activate `.venv`, and call `python setup.py "$@"`.

#### 🎯 Acceptance Criteria
- Running `./install.sh` in interactive mode presents a clean CLI menu and installs only the requested TTS dependencies.
- Running `./install.sh --engine=piper --quiet` installs core + piper requirements in non-interactive mode.
- The `.env` file reflects the chosen engine default after setup completes.

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
  - Call `setup.ensure_env_configured()` before launching uvicorn or background worker.
  - If `.env` is missing, auto-generate `.env` with secure keys silently or with a brief notification log.
  - Ensure `/data` subdirectories exist.
- [ ] **Task 2.1.2**: Add `--setup` CLI flag to `start.py` (`python start.py --setup`) to trigger the interactive `setup.py` wizard directly from the launcher.
- [ ] **Task 2.1.3**: Update `start.sh` shell script to check for `.venv` and notify user if running in system Python vs virtual environment.

#### 🎯 Acceptance Criteria
- Running `python start.py` on a freshly cloned repo without `.env` auto-generates `.env` and `/data` dirs, launching the application smoothly on port 8000.
- Running `python start.py --setup` launches the interactive setup wizard.

---

## 📋 Feature 3: Docker & Containerized Deployment

### 👤 User Story 3.1: Single-Command Docker Deployment
> **As a** DevOps engineer or home-lab user,  
> **I want** a production-ready `Dockerfile` and `docker-compose.yml`,  
> **So that** I can deploy VibeListen with a single command (`docker compose up -d`).

#### 🛠️ Tasks
- [ ] **Task 3.1.1**: Create multi-stage `Dockerfile`:
  - Base image: `python:3.11-slim` or `python:3.13-slim`.
  - Install system dependencies (`ffmpeg`, `curl`, build essentials).
  - Copy `requirements.txt` and install pip dependencies.
  - Copy application code.
  - Set entrypoint: `python start.py`.
- [ ] **Task 3.1.2**: Create `.dockerignore` file excluding `.venv`, `__pycache__`, `.pytest_cache`, and local SQLite database files.
- [ ] **Task 3.1.3**: Create `docker-compose.yml`:
  - Service: `vibelisten`
  - Port mapping: `8000:8000`
  - Volume mount: `./data:/app/data`
  - Env file: `.env`
  - Restart policy: `unless-stopped`

#### 🎯 Acceptance Criteria
- `docker compose up -d --build` builds the container image cleanly.
- Container starts FastAPI and worker via `start.py`.
- Application is accessible at `http://localhost:8000`.
- Data, database, audio, and models persist across container restarts in `./data`.

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
2. `python -m pytest` passes 100%.
3. Fresh local installation via `./install.sh` verified on Linux/macOS.
4. Fresh Docker installation via `docker compose up -d` verified.
