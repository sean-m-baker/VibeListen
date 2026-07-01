import pytest
from cryptography.fernet import Fernet, InvalidToken

from backend import config
from backend.auth import (
    encrypt_secret,
    decrypt_secret,
    is_secret_key,
    secret_redactor,
    is_internal_ip,
    sanitize_filename,
    REDACTED_SECRET_KEYS,
)


class TestEncryption:
    """Fernet encrypt/decrypt round-trip and edge cases."""

    def test_encrypt_decrypt_round_trip(self):
        plaintext = "my-super-secret-api-token-12345"
        cipher = encrypt_secret(plaintext)
        assert cipher != plaintext
        assert decrypt_secret(cipher) == plaintext

    def test_encrypt_different_each_time(self):
        """Same plaintext should produce different ciphertext (Fernet uses IV)."""
        plaintext = "constant-value"
        c1 = encrypt_secret(plaintext)
        c2 = encrypt_secret(plaintext)
        assert c1 != c2
        assert decrypt_secret(c1) == decrypt_secret(c2) == plaintext

    def test_decrypt_plaintext_passthrough(self):
        """Pre-migration plaintext values should pass through without crashing."""
        assert decrypt_secret("plaintext-value") == "plaintext-value"

    def test_decrypt_garbage_returns_as_is(self):
        """Garbage that isn't valid ciphertext should pass through."""
        assert decrypt_secret("not-encrypted-at-all!!!") == "not-encrypted-at-all!!!"

    def test_encrypt_empty_string(self):
        cipher = encrypt_secret("")
        assert decrypt_secret(cipher) == ""


class TestSecretKeyDetection:
    """is_secret_key and REDACTED_SECRET_KEYS."""

    def test_known_secret_keys(self):
        assert is_secret_key("raindrop_token")
        assert is_secret_key("instapaper_password")
        assert is_secret_key("instapaper_consumer_secret")
        assert is_secret_key("instapaper_consumer_key")

    def test_non_secret_keys(self):
        assert not is_secret_key("tts_engine")
        assert not is_secret_key("max_rss_items")
        assert not is_secret_key("audio_bitrate")

    def test_case_insensitive(self):
        assert is_secret_key("Raindrop_Token")
        assert is_secret_key("API_SECRET")

    def test_redacted_set_contains_expected(self):
        assert REDACTED_SECRET_KEYS == {"token", "secret", "password", "key"}


class TestSecretRedactor:
    def test_always_returns_redacted(self):
        assert secret_redactor("anything") == "***REDACTED***"
        assert secret_redactor("") == "***REDACTED***"


class TestInternalIP:
    """SSRF prevention — private / reserved IP detection."""

    def test_loopback(self):
        assert is_internal_ip("127.0.0.1") is True
        assert is_internal_ip("127.255.255.255") is True

    def test_rfc1918(self):
        assert is_internal_ip("10.0.0.1") is True
        assert is_internal_ip("10.255.255.255") is True
        assert is_internal_ip("172.16.0.1") is True
        assert is_internal_ip("172.31.255.255") is True
        assert is_internal_ip("192.168.0.1") is True
        assert is_internal_ip("192.168.255.255") is True

    def test_link_local(self):
        assert is_internal_ip("169.254.169.254") is True

    def test_ipv6_loopback(self):
        assert is_internal_ip("::1") is True

    def test_public_ip(self):
        assert is_internal_ip("8.8.8.8") is False
        assert is_internal_ip("1.1.1.1") is False
        assert is_internal_ip("93.184.216.34") is False  # example.com

    def test_non_ip_string(self):
        """Non-IP strings should return False (no resolution attempted)."""
        assert is_internal_ip("example.com") is False
        assert is_internal_ip("localhost") is False


class TestSanitizeFilename:
    """Path-traversal prevention for filenames."""

    def test_normal_filename_preserved(self):
        assert sanitize_filename("raindrop_12345.wav") == "raindrop_12345.wav"

    def test_traversal_sequences_stripped(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result
        assert result  # should not be empty

    def test_backslash_stripped(self):
        result = sanitize_filename("..\\..\\windows\\system32")
        assert "\\" not in result
        assert result

    def test_spaces_removed(self):
        assert sanitize_filename("hello world.txt") == "helloworld.txt"

    def test_special_chars_removed(self):
        result = sanitize_filename('file<>:"/|?*.wav')
        assert "/" not in result
        assert ":" not in result
        assert "|" not in result
        assert result.endswith(".wav")  # extension preserved

    def test_empty_input_returns_default(self):
        assert sanitize_filename("") == "untitled"

    def test_only_unsafe_chars_returns_default(self):
        assert sanitize_filename("   ") == "untitled"
