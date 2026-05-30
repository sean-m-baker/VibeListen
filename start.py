#!/usr/bin/env python3
"""
VibeListen Launcher
================
Starts both the FastAPI web server and the background worker in parallel,
with cross-platform graceful shutdown on Ctrl+C or SIGTERM.

Usage:
    python start.py
"""

import os
import subprocess
import sys
import signal
import time
from pathlib import Path

# Determine the project root (directory containing this script)
PROJECT_ROOT = Path(__file__).resolve().parent

SERVER_CMD = [
    sys.executable, "-m", "uvicorn", "backend.main:app",
    "--host", "0.0.0.0", "--port", "8000",
]
WORKER_CMD = [sys.executable, "backend/worker.py"]

processes = []


def shutdown():
    """Terminate all child processes gracefully."""
    print("\n[Launcher] Shutting down processes...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    # Give processes a moment to exit cleanly
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    print("[Launcher] All processes stopped.")


def signal_handler(signum, frame):
    shutdown()
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    print("[Launcher] Starting VibeListen server and worker...")
    print(f"[Launcher] Project root: {PROJECT_ROOT}")

    # Ensure Python imports resolve from the project root
    env = os.environ.copy()
    existing_py_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    if existing_py_path:
        env["PYTHONPATH"] += os.pathsep + existing_py_path

    cwd = str(PROJECT_ROOT)

    server = subprocess.Popen(SERVER_CMD, cwd=cwd, env=env)
    worker = subprocess.Popen(WORKER_CMD, cwd=cwd, env=env)
    processes = [server, worker]

    print("[Launcher] Both processes started. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
            # If any process exits unexpectedly, shut everything down
            if any(p.poll() is not None for p in processes):
                print("[Launcher] A process exited unexpectedly.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
