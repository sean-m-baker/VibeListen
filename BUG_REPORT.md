# 🐛 Bug Report: Setup, Launcher, and Docker Deployment Fixes

**Target Audience**: Developer / Implementing AI Agent  
**Date**: July 29, 2026  
**Source Branch**: `v0.7`  
**Status**: Open  

---

## 📋 Summary of Findings

During code review of the installation streamlining implementation ([setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py), [start.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/start.py), [Dockerfile](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/Dockerfile), [docker-entrypoint.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/docker-entrypoint.sh)), **5 issues** were identified: 1 High Severity, 2 Medium Severity, and 2 Low Severity bugs.

Below are the detailed bug specifications, reproduction steps, expected behavior, and exact code resolution instructions.

---

## 🔴 [BUG-01] Existing `.env` with Blank or Missing Keys Skips Generation & Crashes Server

- **Severity**: High
- **Type**: Bug / App Crash
- **File**: [setup.py:L189-L212](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L189-L212)
- **Functions Affected**: `ensure_env_configured()`

### Description
`ensure_env_configured()` currently checks `if not env_path.exists():` before generating `SECRET_KEY` and `ENCRYPTION_KEY`. If `.env` already exists (e.g., created manually or copied from `.env.example` where keys are blank: `SECRET_KEY=`), `setup.py` prints:
`[Setup] .env already exists — skipping generation`

When `python start.py` or FastAPI (`backend/config.py`) runs, `config.py` raises `RuntimeError("SECRET_KEY environment variable is required...")` and crashes the application on startup.

### Expected Behavior
`ensure_env_configured()` should check existing `.env` files for blank or missing `SECRET_KEY` and `ENCRYPTION_KEY` values and automatically inject valid generated Fernet keys.

### Resolution Instructions
In [setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L189-L212), update `ensure_env_configured()` to inspect and inject missing/empty keys into existing `.env` files:

```python
    if not env_path.exists():
        if env_example.exists():
            shutil.copy(str(env_example), str(env_path))
            print("[Setup] Created .env from .env.example")
        else:
            env_path.write_text("# VibeListen Environment Configuration\n\n")
            print("[Setup] Created minimal .env (no .env.example found)")
        result["env_created"] = True

    # Inspect and generate Fernet keys if blank or missing
    raw = env_path.read_text()
    env_vars: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env_vars[k.strip()] = v.strip()

    updated = False
    if not env_vars.get("SECRET_KEY"):
        raw = _inject_key(raw, "SECRET_KEY", generate_fernet_key())
        updated = True
    if not env_vars.get("ENCRYPTION_KEY"):
        raw = _inject_key(raw, "ENCRYPTION_KEY", generate_fernet_key())
        updated = True

    if updated:
        env_path.write_text(raw)
        print("[Setup] Generated missing SECRET_KEY / ENCRYPTION_KEY in .env")
    else:
        print("[Setup] .env configuration keys OK")
```

---

## 🟡 [BUG-02] Fallback to `edge` Engine Clears `TTS_ENGINE_FAILED` Diagnostic Flag

- **Severity**: Medium
- **Type**: User Story Violation / Diagnostic Defect
- **File**: [setup.py:L296-L316](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L296-L316) & [setup.py:L422-L426](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L422-L426)
- **Functions Affected**: `_write_engine_env()`, `main()`

### Description
**User Story 1.2.3a** requires that when a TTS engine pip install fails in quiet/non-interactive mode, setup falls back to `edge` while setting `TTS_ENGINE_FAILED=<failed_file>` in `.env` for diagnostics.

Currently, when `install_tts_deps()` fails, it calls `_write_engine_env("pocket", ["requirements-pocket.txt"])`. Then `main()` calls `_write_engine_env("edge", [])` to set the fallback. Because `failed` is passed as an empty list `[]`, `_write_engine_env()` strips `TTS_ENGINE_FAILED=` out of `.env`, erasing the failure diagnostic log immediately after fallback.

### Expected Behavior
Falling back to `edge` should write `TTS_ENGINE=edge` while retaining `TTS_ENGINE_FAILED=<failed_reqs>` in `.env`.

### Resolution Instructions
Update `_write_engine_env()` in [setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L296-L316) so that fallback calls preserve previous failure info, or pass `failed=failed` when falling back to `edge`:

```python
def _write_engine_env(engine: str, failed: list[str] | None = None, project_root: Path | None = None) -> None:
    if project_root is None:
        project_root = Path(__file__).resolve().parent
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    raw = env_path.read_text()
    raw = _inject_key(raw, "TTS_ENGINE", engine)

    if failed:
        raw = _inject_key(raw, "TTS_ENGINE_FAILED", ",".join(failed))

    env_path.write_text(raw)
    print(f"[Setup] TTS_ENGINE set to '{engine}' in .env")
```

In `main()` lines 422–426:
```python
        install_ok = install_tts_deps(engine, quiet=args.quiet)
        if not install_ok and engine != "edge":
            print(f"\n  Falling back to 'edge' engine.")
            _write_engine_env("edge", failed=ENGINE_REQUIREMENTS.get(engine, []))
            print("  TTS_ENGINE set to 'edge' in .env")
```

---

## 🟡 [BUG-03] Multi-Stage Docker COPY Neglects User Binaries & C++ Shared Libraries

- **Severity**: Medium
- **Type**: Docker / Build Risk
- **File**: [Dockerfile:L51-L53](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/Dockerfile#L51-L53)
- **Stage Affected**: Runtime stage

### Description
In `Dockerfile`, the runtime stage copies python packages from builder:
```dockerfile
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
```
Packages like `piper-tts`, `onnxruntime`, `moshi`, and `sphn` include native binary `.so` objects and user-space binaries. Copying `/usr/local/bin` directly over runtime binaries can cause library link mismatch or broken CLI entrypoints.

### Expected Behavior
Python packages should be installed in a clean user space (`/root/.local`) or installed directly in the runtime image.

### Resolution Instructions
In [Dockerfile](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/Dockerfile), update the builder and runtime stages to use `pip install --user`:

```dockerfile
# Builder Stage
FROM python:3.11-slim AS builder
ARG TTS_PROFILE=all
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt
RUN if [ "$TTS_PROFILE" != "edge" ]; then \
        pip install --user --no-cache-dir -r requirements-local.txt; \
    fi

# Runtime Stage
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .
RUN chmod +x /app/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "start.py"]
```

---

## 🟢 [BUG-04] Fragile Literal Replace for `RAINDROP_TOKEN` in `setup.py`

- **Severity**: Low
- **Type**: UX / Fragility
- **File**: [setup.py:L333-L336](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L333-L336)
- **Function Affected**: `_prompt_raindrop_token()`

### Description
`_prompt_raindrop_token()` uses exact string replacement:
`raw.replace("RAINDROP_TOKEN=your_raindrop_personal_test_token_here", f"RAINDROP_TOKEN={token}")`
If `.env` does not contain that exact default placeholder string, user input is silently discarded.

### Expected Behavior
`_prompt_raindrop_token()` should inject `RAINDROP_TOKEN` reliably regardless of original placeholder text.

### Resolution Instructions
In [setup.py](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/setup.py#L322-L339), update `_prompt_raindrop_token()` to use `_inject_key`:

```python
def _prompt_raindrop_token(project_root: Path) -> None:
    token = input("\nRaindrop.io token (optional, press Enter to skip): ").strip()
    if not token:
        return

    env_path = project_root / ".env"
    if not env_path.exists():
        return

    raw = env_path.read_text()
    raw = _inject_key(raw, "RAINDROP_TOKEN", token)
    env_path.write_text(raw)
    print("[Setup] RAINDROP_TOKEN saved to .env")
```

---

## 🟢 [BUG-05] Non-Executable File Mode on `docker-entrypoint.sh`

- **Severity**: Low
- **Type**: File Permission
- **File**: [docker-entrypoint.sh](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/docker-entrypoint.sh)

### Description
`docker-entrypoint.sh` was committed to Git with non-executable mode `100644`.

### Expected Behavior
Shell scripts should have `100755` executable file mode in Git index.

### Resolution Instructions
Run the following git command:
```bash
git update-index --chmod=+x docker-entrypoint.sh
```

---

## 🧪 Verification Plan

After applying the fixes, verify with:

1. **Pytest Suite**:
   ```bash
   .venv/bin/python -m pytest
   ```
2. **Existing `.env` Key Injection Test**:
   ```bash
   echo "SECRET_KEY=" > .env
   .venv/bin/python start.py --quiet
   # Verify SECRET_KEY has been populated in .env
   ```
3. **Docker Build Test**:
   ```bash
   docker compose up -d --build
   ```
