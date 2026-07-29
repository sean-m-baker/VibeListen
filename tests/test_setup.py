"""Tests for the setup.py module — environment bootstrap, diagnostics, and CLI."""

import os
import sys
import base64
import subprocess
from pathlib import Path

import pytest

from setup import (
    generate_fernet_key,
    ensure_data_dirs,
    ensure_env_configured,
    check_python_version,
    check_ffmpeg,
    _inject_key,
    _validate_keys,
    _write_engine_env,
    DATA_SUBDIRS,
)


# ---------------------------------------------------------------------------
# generate_fernet_key
# ---------------------------------------------------------------------------

class TestGenerateFernetKey:
    def test_returns_string(self):
        key = generate_fernet_key()
        assert isinstance(key, str)

    def test_has_correct_length(self):
        key = generate_fernet_key()
        # 32 bytes base64-encoded -> 44 characters + '=' padding -> 44 chars
        assert len(key) == 44

    def test_is_base64_encoded(self):
        key = generate_fernet_key()
        # Should be valid base64 (URL-safe variant)
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_unique_per_call(self):
        keys = {generate_fernet_key() for _ in range(100)}
        assert len(keys) == 100

    def test_accepted_by_fernet(self):
        """Verify key works with cryptography.fernet if available."""
        key = generate_fernet_key()
        try:
            from cryptography.fernet import Fernet
            f = Fernet(key)
            token = f.encrypt(b"test")
            assert f.decrypt(token) == b"test"
        except ImportError:
            pytest.skip("cryptography not installed")


# ---------------------------------------------------------------------------
# ensure_data_dirs
# ---------------------------------------------------------------------------

class TestEnsureDataDirs:
    def test_creates_all_subdirs(self, tmp_path):
        created = ensure_data_dirs(tmp_path)
        assert len(created) == len(DATA_SUBDIRS)
        for sub in DATA_SUBDIRS:
            d = tmp_path / sub
            assert d.is_dir(), f"{d} was not created"

    def test_returns_existing_dirs_on_re_run(self, tmp_path):
        ensure_data_dirs(tmp_path)
        created = ensure_data_dirs(tmp_path)
        assert created == []

    def test_sets_755_permissions(self, tmp_path):
        ensure_data_dirs(tmp_path)
        for sub in DATA_SUBDIRS:
            d = tmp_path / sub
            if os.name != "nt":  # permission check only on Unix
                mode = d.stat().st_mode & 0o777
                assert mode == 0o755, f"{d} has mode {oct(mode)}"


# ---------------------------------------------------------------------------
# ensure_env_configured
# ---------------------------------------------------------------------------

class TestEnsureEnvConfigured:
    def test_creates_env_from_example(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text(
            "# Env\nSECRET_KEY=\nENCRYPTION_KEY=\nTTS_ENGINE=edge\n"
        )
        result = ensure_env_configured(project_root=tmp_path)
        assert result["env_created"] is True
        assert (tmp_path / ".env").exists()

    def test_generates_valid_keys(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text("SECRET_KEY=\nENCRYPTION_KEY=\n")
        ensure_env_configured(project_root=tmp_path)
        env_text = (tmp_path / ".env").read_text()
        assert "SECRET_KEY=" in env_text
        assert "ENCRYPTION_KEY=" in env_text
        # Validate they look like Fernet keys
        for line in env_text.splitlines():
            if line.startswith("SECRET_KEY="):
                val = line.split("=", 1)[1]
                assert len(val) == 44
            elif line.startswith("ENCRYPTION_KEY="):
                val = line.split("=", 1)[1]
                assert len(val) == 44

    def test_does_not_overwrite_existing_env(self, tmp_path):
        (tmp_path / ".env.example").write_text("SECRET_KEY=\nENCRYPTION_KEY=\n")
        (tmp_path / ".env").write_text("MY_VAR=hello\n")
        result = ensure_env_configured(project_root=tmp_path)
        assert result["env_created"] is False
        assert "MY_VAR=hello" in (tmp_path / ".env").read_text()

    def test_creates_data_dirs(self, tmp_path):
        (tmp_path / ".env.example").write_text("SECRET_KEY=\nENCRYPTION_KEY=\n")
        result = ensure_env_configured(project_root=tmp_path)
        assert len(result["dirs_created"]) == len(DATA_SUBDIRS)

    def test_creates_minimal_env_when_no_example(self, tmp_path):
        result = ensure_env_configured(project_root=tmp_path)
        assert result["env_created"] is True
        assert (tmp_path / ".env").exists()

    def test_replaces_commented_out_keys(self, tmp_path):
        """Keys that are commented out (#SECRET_KEY=) should be replaced."""
        example = tmp_path / ".env.example"
        example.write_text("#SECRET_KEY=\n#ENCRYPTION_KEY=\nTTS_ENGINE=edge\n")
        ensure_env_configured(project_root=tmp_path)
        env_text = (tmp_path / ".env").read_text()
        assert "SECRET_KEY=" in env_text
        assert "ENCRYPTION_KEY=" in env_text
        assert not any(l.strip().startswith("#SECRET_KEY=") for l in env_text.splitlines())


# ---------------------------------------------------------------------------
# _inject_key
# ---------------------------------------------------------------------------

class TestInjectKey:
    def test_replaces_empty_key(self):
        content = "SECRET_KEY=\nENCRYPTION_KEY=\n"
        result = _inject_key(content, "SECRET_KEY", "abc123")
        assert "SECRET_KEY=abc123" in result

    def test_appends_if_missing(self):
        content = "OTHER=val\n"
        result = _inject_key(content, "SECRET_KEY", "abc123")
        assert result.strip().endswith("SECRET_KEY=abc123")

    def test_uncomments_key(self):
        content = "#SECRET_KEY=\n"
        result = _inject_key(content, "SECRET_KEY", "abc123")
        assert "SECRET_KEY=abc123" in result
        assert "#SECRET_KEY=" not in result


# ---------------------------------------------------------------------------
# check_python_version
# ---------------------------------------------------------------------------

class TestCheckPythonVersion:
    def test_current_version_passes(self):
        """The test itself is running under a supported Python — should pass."""
        assert check_python_version() is True


# ---------------------------------------------------------------------------
# check_ffmpeg
# ---------------------------------------------------------------------------

class TestCheckFfmpeg:
    def test_ffmpeg_returns_bool(self):
        result = check_ffmpeg()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _validate_keys
# ---------------------------------------------------------------------------

class TestValidateKeys:
    def test_valid_keys_pass(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "SECRET_KEY=ZG8gbm90IGxvb2sgaW4gdGhpcyBmaWxlIGJybw==\n"
            "ENCRYPTION_KEY=VGhpcyBpcyBub3QgcmVhbGx5IGEgZmVybmV0IGtleQ==\n"
        )
        _validate_keys(env_path)
        # Just ensure no exception is raised

    def test_missing_keys_does_not_crash(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("OTHER=val\n")
        _validate_keys(env_path)


# ---------------------------------------------------------------------------
# BUG-01: Existing .env with blank keys gets populated
# ---------------------------------------------------------------------------

class TestExistingEnvWithBlankKeys:
    def test_fills_blank_secret_key(self, tmp_path):
        """Existing .env with blank SECRET_KEY should get a valid key."""
        env = tmp_path / ".env"
        env.write_text("SECRET_KEY=\nENCRYPTION_KEY=abc123\n")
        ensure_env_configured(project_root=tmp_path)
        env_text = env.read_text()
        assert "SECRET_KEY=" in env_text
        val = [l for l in env_text.splitlines() if l.startswith("SECRET_KEY=")][0].split("=", 1)[1]
        assert len(val) == 44

    def test_fills_blank_encryption_key(self, tmp_path):
        """Existing .env with blank ENCRYPTION_KEY should get a valid key."""
        env = tmp_path / ".env"
        env.write_text("SECRET_KEY=abc123\nENCRYPTION_KEY=\n")
        ensure_env_configured(project_root=tmp_path)
        env_text = env.read_text()
        assert "ENCRYPTION_KEY=" in env_text
        val = [l for l in env_text.splitlines() if l.startswith("ENCRYPTION_KEY=")][0].split("=", 1)[1]
        assert len(val) == 44

    def test_does_not_overwrite_valid_keys(self, tmp_path):
        """Existing .env with valid keys should not be touched."""
        env = tmp_path / ".env"
        env.write_text("SECRET_KEY=validkeyherethatis44charslong!!\nENCRYPTION_KEY=anothervalidkeyfortesting!!!!!\nMY_VAR=hello\n")
        ensure_env_configured(project_root=tmp_path)
        env_text = env.read_text()
        assert "MY_VAR=hello" in env_text
        assert "validkeyherethatis44charslong!!" in env_text


# ---------------------------------------------------------------------------
# _write_engine_env  (BUG-02: preserves TTS_ENGINE_FAILED on fallback)
# ---------------------------------------------------------------------------

class TestWriteEngineEnv:
    def test_preserves_failed_when_none(self, tmp_path):
        """Calling _write_engine_env with failed=None should not touch TTS_ENGINE_FAILED."""
        env = tmp_path / ".env"
        env.write_text("TTS_ENGINE=pocket\nTTS_ENGINE_FAILED=requirements-pocket.txt\n")
        _write_engine_env("edge", failed=None, project_root=tmp_path)
        env_text = env.read_text()
        assert "TTS_ENGINE=edge" in env_text
        assert "TTS_ENGINE_FAILED=requirements-pocket.txt" in env_text

    def test_clears_failed_when_empty_list(self, tmp_path):
        """Calling _write_engine_env with failed=[] should clear TTS_ENGINE_FAILED."""
        env = tmp_path / ".env"
        env.write_text("TTS_ENGINE=pocket\nTTS_ENGINE_FAILED=requirements-pocket.txt\n")
        _write_engine_env("edge", failed=[], project_root=tmp_path)
        env_text = env.read_text()
        assert "TTS_ENGINE=edge" in env_text
        assert "TTS_ENGINE_FAILED=" not in env_text

    def test_sets_failed_when_provided(self, tmp_path):
        """Calling _write_engine_env with a failed list should set TTS_ENGINE_FAILED."""
        env = tmp_path / ".env"
        env.write_text("TTS_ENGINE=edge\n")
        _write_engine_env("pocket", failed=["requirements-pocket.txt"], project_root=tmp_path)
        env_text = env.read_text()
        assert "TTS_ENGINE=pocket" in env_text
        assert "TTS_ENGINE_FAILED=requirements-pocket.txt" in env_text

    def test_updates_default_voice(self, tmp_path):
        """_write_engine_env should update DEFAULT_VOICE to match chosen engine."""
        env = tmp_path / ".env"
        env.write_text("TTS_ENGINE=edge\nDEFAULT_VOICE=en-US-AvaNeural\n")
        _write_engine_env("piper", project_root=tmp_path)
        env_text = env.read_text()
        assert "TTS_ENGINE=piper" in env_text
        assert "DEFAULT_VOICE=en_US-lessac-medium" in env_text

        _write_engine_env("pocket", project_root=tmp_path)
        env_text = env.read_text()
        assert "TTS_ENGINE=pocket" in env_text
        assert "DEFAULT_VOICE=default" in env_text
