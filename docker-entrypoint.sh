#!/bin/sh
# VibeListen Docker entrypoint
# Auto-bootstrap .env and data directories on container start.

set -e

cd /app

# Bootstrap .env if missing and ensure data directories exist
python -c "
from setup import ensure_data_dirs, ensure_env_configured
ensure_data_dirs()
ensure_env_configured(quiet=True)
"

exec "$@"
