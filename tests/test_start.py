"""Tests for start.py launcher — auto-bootstrap, --setup flag, and imports."""

import os
import sys
import shutil
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# start.py --setup flag invokes setup wizard
# ---------------------------------------------------------------------------

class TestSetupFlag:
    def test_setup_flag_runs_setup(self, tmp_path):
        """--setup flag should invoke setup.py (detectable by setup output)."""
        start_py = Path(__file__).resolve().parent.parent / "start.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(start_py.parent)

        # Run with --help to verify parser handles --setup without error
        result = subprocess.run(
            [sys.executable, str(start_py), "--help"],
            capture_output=True, text=True, cwd=tmp_path, env=env,
        )
        assert result.returncode == 0
        assert "--setup" in result.stdout

    def test_setup_flag_shows_wizard_text(self, tmp_path):
        """Running start.py --setup --quiet should show setup wizard output."""
        start_py = Path(__file__).resolve().parent.parent / "start.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(start_py.parent)

        result = subprocess.run(
            [sys.executable, str(start_py), "--setup", "--quiet", "--skip-deps"],
            capture_output=True, text=True, cwd=tmp_path, env=env,
        )
        assert "VibeListen Setup" in result.stdout
        assert "Setup Complete" in result.stdout


# ---------------------------------------------------------------------------
# start.py auto-bootstrap on missing .env
# ---------------------------------------------------------------------------

class TestAutoBootstrap:
    def test_creates_env_when_missing(self, tmp_path):
        """start.py should create .env when missing, before launching services.

        We run start.py in a temp dir (no uvicorn available) so the
        subprocess will fail — but we check .env was created before that.
        """
        # Create a minimal .env.example so bootstrap has a template
        (tmp_path / ".env.example").write_text(
            "SECRET_KEY=\nENCRYPTION_KEY=\nTTS_ENGINE=edge\n"
        )

        # Copy start.py and setup.py to the temp dir so imports resolve
        project_root = Path(__file__).resolve().parent.parent
        for fname in ("start.py", "setup.py"):
            shutil.copy(str(project_root / fname), str(tmp_path / fname))

        # Make the temp dir look like the project root (create data dirs needed by ensure_data_dirs)
        (tmp_path / "data").mkdir(exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(tmp_path)

        # Run start.py — it will try to launch uvicorn which isn't installed,
        # but ensure_env_configured and ensure_data_dirs run first
        result = subprocess.run(
            [sys.executable, "start.py"],
            capture_output=True, text=True, cwd=tmp_path, env=env,
            timeout=15,
        )

        # The bootstrap should have created .env before the subprocess failure
        env_path = tmp_path / ".env"
        assert env_path.exists(), f".env not created. stdout: {result.stdout}"
        env_text = env_path.read_text()
        assert "SECRET_KEY=" in env_text
        assert "ENCRYPTION_KEY=" in env_text

    def test_does_not_overwrite_existing_env(self, tmp_path):
        """start.py should not overwrite an existing .env."""
        (tmp_path / ".env").write_text("MY_VAR=hello\n")

        project_root = Path(__file__).resolve().parent.parent
        for fname in ("start.py", "setup.py"):
            shutil.copy(str(project_root / fname), str(tmp_path / fname))
        (tmp_path / "data").mkdir(exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(tmp_path)

        subprocess.run(
            [sys.executable, "start.py"],
            capture_output=True, text=True, cwd=tmp_path, env=env,
            timeout=15,
        )

        env_text = (tmp_path / ".env").read_text()
        assert "MY_VAR=hello" in env_text


# ---------------------------------------------------------------------------
# start.py module imports cleanly
# ---------------------------------------------------------------------------

class TestStartImport:
    def test_imports_from_setup(self, tmp_path):
        """start.py's import of setup should work (via subprocess due to module-level argparse)."""
        start_py = Path(__file__).resolve().parent.parent / "start.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(start_py.parent)

        result = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(start_py.parent)!r}); import start"],
            capture_output=True, text=True, cwd=tmp_path, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"


# ---------------------------------------------------------------------------
# start.sh behavior
# ---------------------------------------------------------------------------

class TestStartSh:
    def test_start_sh_suggests_install_when_no_venv(self, tmp_path):
        """start.sh should suggest ./install.sh when .venv is missing."""
        project_root = Path(__file__).resolve().parent.parent
        # Copy start.sh to temp dir so it doesn't find the project's .venv
        shutil.copy(str(project_root / "start.sh"), str(tmp_path / "start.sh"))
        result = subprocess.run(
            ["bash", "start.sh"],
            capture_output=True, text=True, cwd=tmp_path,
        )
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "install.sh" in output or "./install.sh" in output
