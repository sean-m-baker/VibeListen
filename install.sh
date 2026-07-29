#!/usr/bin/env bash
# VibeListen Installer (Unix)
# One-command local setup — creates virtualenv, installs deps, configures .env.
#
# Usage:
#     ./install.sh                    # interactive mode
#     ./install.sh --engine=piper     # non-interactive with engine selection
#     ./install.sh --quiet            # accept all defaults (edge TTS)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------------
# Pre-flight: check for python3
# ------------------------------------------------------------------
if ! command -v python3 &>/dev/null; then
    echo "[Error] python3 not found. Please install Python ${MIN_PYTHON:-3.10}+."
    exit 1
fi

# ------------------------------------------------------------------
# Virtual environment
# ------------------------------------------------------------------
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[Install] Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    echo "[Install] Virtual environment created at .venv"
fi

# shellcheck source=/dev/null
. "$SCRIPT_DIR/.venv/bin/activate"

echo "[Install] Using Python: $(command -v python3) ($(python3 --version 2>&1))"

# ------------------------------------------------------------------
# Delegate to setup.py
# ------------------------------------------------------------------
echo "[Install] Running setup wizard..."
exec python "$SCRIPT_DIR/setup.py" "$@"
