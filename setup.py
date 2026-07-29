#!/usr/bin/env python3
"""
VibeListen Setup Wizard
=====================
Automated environment bootstrap, dependency installation, and pre-flight diagnostics.
Dual-mode: importable module + standalone CLI script.

Usage:
    python setup.py                    # interactive mode
    python setup.py --quiet            # non-interactive with defaults
    python setup.py --engine=piper     # non-interactive with specific engine
"""

import os
import sys
import base64
import shutil
import subprocess
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Fernet key generation (stdlib only — no cryptography dependency required)
# ---------------------------------------------------------------------------

def generate_fernet_key() -> str:
    """Generate a cryptographically secure Fernet key using stdlib only.

    Fernet keys are 32 random bytes base64-encoded (44 chars).
    Validated against ``cryptography.fernet.Fernet`` after core deps install.
    """
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


# ---------------------------------------------------------------------------
# Data directory bootstrap
# ---------------------------------------------------------------------------

DATA_SUBDIRS = [
    "data",
    "data/audio",
    "data/audio_cache",
    "data/models",
]


def ensure_data_dirs(project_root: Path | None = None) -> list[Path]:
    """Create required runtime data directories if they don't exist.

    Returns a list of newly-created directories.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent

    created: list[Path] = []
    for sub in DATA_SUBDIRS:
        d = project_root / sub
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            d.chmod(0o755)
            created.append(d)
    return created


# ---------------------------------------------------------------------------
# Pre-flight diagnostics
# ---------------------------------------------------------------------------

MIN_PYTHON = (3, 10)
RECOMMEND_PYTHON = (3, 13)


def check_python_version() -> bool:
    """Validate Python version >= 3.10. Returns True if OK."""
    current = sys.version_info[:2]
    if current < MIN_PYTHON:
        print(
            f"[Error] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required; "
            f"found {current[0]}.{current[1]}"
        )
        return False
    if current < RECOMMEND_PYTHON:
        print(
            f"[Warning] Python {RECOMMEND_PYTHON[0]}.{RECOMMEND_PYTHON[1]}+ recommended; "
            f"found {current[0]}.{current[1]}"
        )
    return True


def _print_ffmpeg_install_help() -> None:
    """Print OS-specific ffmpeg installation instructions."""
    system = sys.platform
    if system == "linux":
        try:
            with open("/etc/os-release") as f:
                data = f.read().lower()
        except FileNotFoundError:
            data = ""

        if "ubuntu" in data or "debian" in data:
            print("    Ubuntu/Debian: sudo apt install ffmpeg")
        elif "arch" in data:
            print("    Arch: sudo pacman -S ffmpeg")
        elif "fedora" in data:
            print("    Fedora: sudo dnf install ffmpeg")
        else:
            print("    Linux: sudo apt install ffmpeg  (or use your package manager)")
    elif system == "darwin":
        print("    macOS: brew install ffmpeg")
    elif system == "win32":
        print("    Windows: choco install ffmpeg  (or download from https://ffmpeg.org/)")
    else:
        print(f"    Please install ffmpeg for your OS ({system})")


def check_ffmpeg() -> bool:
    """Check if ``ffmpeg`` is available on PATH. Returns True if found."""
    if shutil.which("ffmpeg"):
        return True

    print("[Warning] ffmpeg not found on PATH.")
    print("  ffmpeg is required for audio transcoding. Install it:")
    _print_ffmpeg_install_help()
    return False


# ---------------------------------------------------------------------------
# Environment configuration (.env bootstrap)
# ---------------------------------------------------------------------------

def _inject_key(content: str, key_name: str, key_value: str) -> str:
    """Replace or append a key in dotenv content."""
    lines = content.splitlines()
    new_lines: list[str] = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key_name}="):
            new_lines.append(f"{key_name}={key_value}")
            found = True
        elif stripped.startswith(f"#{key_name}="):
            new_lines.append(f"{key_name}={key_value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key_name}={key_value}")
    return "\n".join(new_lines) + "\n"


def ensure_env_configured(
    interactive: bool = False,
    engine: str | None = None,
    quiet: bool = False,
    project_root: Path | None = None,
) -> dict:
    """Bootstrap ``.env`` and runtime data directories.

    Parameters
    ----------
    interactive : bool
        Whether to prompt for optional values (Raindrop token).
    engine : str or None
        TTS engine to write into ``.env``.  Defaults to ``"edge"``.
    quiet : bool
        If True, skip interactive prompts.
    project_root : Path or None
        Root directory for ``.env`` and data dirs.  Defaults to parent of this file.

    Returns
    -------
    dict
        Status summary with keys ``env_created``, ``dirs_created``, ``engine``.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent
    env_path = project_root / ".env"
    env_example = project_root / ".env.example"

    result: dict = {
        "env_created": False,
        "dirs_created": [],
        "engine": engine or "edge",
    }

    result["dirs_created"] = [str(d) for d in ensure_data_dirs(project_root)]

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

    _validate_keys(env_path)

    return result


def _validate_keys(env_path: Path) -> None:
    """Validate Fernet keys in .env if ``cryptography`` is installed."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("[Setup] cryptography not available — skipping key validation")
        return

    env_vars: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            env_vars[key.strip()] = val.strip()

    for name in ("SECRET_KEY", "ENCRYPTION_KEY"):
        val = env_vars.get(name)
        if val:
            try:
                Fernet(val)
                print(f"[Setup] {name} validates OK")
            except Exception as exc:
                print(f"[Error] {name} is invalid: {exc}")
        else:
            print(f"[Warning] {name} not found in .env")


# ---------------------------------------------------------------------------
# TTS dependency installation
# ---------------------------------------------------------------------------

ENGINE_REQUIREMENTS: dict[str, list[str]] = {
    "edge": ["requirements.txt"],
    "piper": ["requirements.txt", "requirements-piper.txt"],
    "pocket": ["requirements.txt", "requirements-pocket.txt"],
    "all": ["requirements.txt", "requirements-local.txt"],
}

ENGINE_DEFAULT_VOICES: dict[str, str] = {
    "edge": "en-US-AvaNeural",
    "piper": "en_US-lessac-medium",
    "pocket": "default",
    "all": "en-US-AvaNeural",
}


def install_tts_deps(engine: str, quiet: bool = False, project_root: Path | None = None) -> bool:
    """Install Python dependencies for the selected TTS engine.

    Returns True if all required ``pip install`` commands succeeded.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent
    req_files = ENGINE_REQUIREMENTS.get(engine, ENGINE_REQUIREMENTS["edge"])

    all_ok = True
    failed: list[str] = []

    for req_file in req_files:
        req_path = project_root / req_file
        if not req_path.exists():
            print(f"  [Skip] {req_file} not found")
            continue

        print(f"  [Install] pip install -r {req_file} ...", end=" ")
        sys.stdout.flush()

        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            print("OK")
        else:
            print("FAILED")
            print(f"    {proc.stderr.strip()}")
            all_ok = False
            failed.append(req_file)

    _write_engine_env(engine, failed)

    if failed:
        print(f"\n[Warning] {len(failed)} requirement(s) failed: {', '.join(failed)}")

    return all_ok


def _write_engine_env(engine: str, failed: list[str] | None = None, project_root: Path | None = None) -> None:
    """Persist engine selection and failure info to ``.env``.

    Parameters
    ----------
    engine : str
        TTS engine name to write.
    failed : list[str] or None
        List of failed requirement files.  If None, ``TTS_ENGINE_FAILED``
        is left unchanged.  If an empty list, ``TTS_ENGINE_FAILED`` is cleared.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    raw = env_path.read_text()
    raw = _inject_key(raw, "TTS_ENGINE", engine)
    if engine in ENGINE_DEFAULT_VOICES:
        raw = _inject_key(raw, "DEFAULT_VOICE", ENGINE_DEFAULT_VOICES[engine])

    if failed is not None:
        if failed:
            raw = _inject_key(raw, "TTS_ENGINE_FAILED", ",".join(failed))
        else:
            lines = raw.splitlines()
            lines = [l for l in lines if not l.strip().startswith("TTS_ENGINE_FAILED=")]
            raw = "\n".join(lines) + "\n"

    env_path.write_text(raw)
    print(f"[Setup] TTS_ENGINE set to '{engine}' in .env")


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def _prompt_raindrop_token(project_root: Path) -> None:
    """Prompt for Raindrop.io token and write to .env."""
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


def interactive_wizard() -> str:
    """Run interactive TTS engine selection. Returns chosen engine name."""
    print("\n=== VibeListen Setup Wizard ===\n")
    print("Select TTS Engine:")
    print("  1) edge    — Cloud-based (default, lightweight)")
    print("  2) piper   — Local ONNX (~50 MB)")
    print("  3) pocket  — Local PyTorch/CALM (~3 GB, GPU recommended)")
    print("  4) all     — Install everything\n")

    while True:
        choice = input("Choice [1]: ").strip() or "1"
        mapping = {"1": "edge", "2": "piper", "3": "pocket", "4": "all"}
        if choice in mapping:
            return mapping[choice]
        print("Invalid choice. Please enter 1-4.")


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="VibeListen Setup Wizard — bootstrap, install & diagnose."
    )
    parser.add_argument(
        "--engine",
        choices=["edge", "piper", "pocket", "all"],
        help="TTS engine to configure (skips interactive prompt)",
    )
    parser.add_argument(
        "--quiet", "-y",
        action="store_true",
        help="Non-interactive mode with defaults",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip pip dependency installation",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent

    print("=== VibeListen Setup ===\n")

    # 1. Pre-flight diagnostics
    print("[1/4] Pre-flight checks")
    if not check_python_version():
        sys.exit(1)
    check_ffmpeg()
    print()

    # 2. Environment bootstrap
    print("[2/4] Environment bootstrap")
    result = ensure_env_configured(
        interactive=bool(not args.quiet and not args.engine),
        engine=args.engine or "edge",
        quiet=args.quiet,
    )
    print()

    # 3. TTS engine selection
    print("[3/4] TTS engine selection")
    if args.engine:
        engine = args.engine
        print(f"  Using: {engine}")
    elif args.quiet:
        engine = "edge"
        print(f"  Default: {engine}")
    else:
        engine = interactive_wizard()
        _write_engine_env(engine, [])
        _prompt_raindrop_token(project_root)
    print()

    # 4. Dependency installation
    print(f"[4/4] Dependency installation (engine: {engine})")
    if args.skip_deps:
        print("  [Skip] --skip-deps flag set")
    else:
        install_ok = install_tts_deps(engine, quiet=args.quiet)
        if not install_ok and engine != "edge":
            print(f"\n  Falling back to 'edge' engine.")
            _write_engine_env("edge", failed=ENGINE_REQUIREMENTS.get(engine, []))
            print("  TTS_ENGINE set to 'edge' in .env")
    print()

    print("=== Setup Complete ===")
    print(f"  Engine:     {engine}")
    print(f"  ffmpeg:     {'found' if shutil.which('ffmpeg') else 'missing (see warning)'}")
    print(f"  Python:     {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print("\nNext step:  python start.py")


if __name__ == "__main__":
    main()
