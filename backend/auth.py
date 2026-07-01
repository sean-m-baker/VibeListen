import ipaddress
import logging
import socket
import re
from functools import lru_cache
from typing import Set

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from backend import config

logger = logging.getLogger("VibeListen.Auth")

# Fernet cipher for encrypting/decrypting secrets at rest
_fernet = Fernet(
    config.SECRET_KEY.encode() if isinstance(config.SECRET_KEY, str) else config.SECRET_KEY
)

# Key name substrings whose values are considered secret and should be
# encrypted at rest and redacted in API responses.
REDACTED_SECRET_KEYS: Set[str] = {
    "token", "secret", "password", "key",
}


# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

async def require_api_key(request: Request) -> None:
    """FastAPI dependency — reject requests without a valid X-API-Key header."""
    key = request.headers.get("X-API-Key", "")
    if not key or key != config.SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------

async def require_csrf_header(request: Request) -> None:
    """FastAPI dependency — reject POST requests missing the custom CSRF header."""
    if request.headers.get("X-Requested-By") != "VibeListen":
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid CSRF header. Set X-Requested-By: VibeListen",
        )


# ---------------------------------------------------------------------------
# Fernet encryption / decryption for credential storage
# ---------------------------------------------------------------------------

def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret value for storage in the database."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a ciphertext secret value retrieved from the database."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("Failed to decrypt secret — value may be plaintext from a previous version")
        return ciphertext


# ---------------------------------------------------------------------------
# Secret redaction (for API responses)
# ---------------------------------------------------------------------------

def is_secret_key(key_name: str) -> bool:
    """Return True if *key_name* indicates a sensitive value."""
    key_lower = key_name.lower()
    return any(kw in key_lower for kw in REDACTED_SECRET_KEYS)


def secret_redactor(_value: str) -> str:
    """Return a redacted placeholder — the original value is never exposed."""
    return "***REDACTED***"


# ---------------------------------------------------------------------------
# Internal IP detection (SSRF prevention)
# ---------------------------------------------------------------------------

_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]


@lru_cache(maxsize=1024)
def is_internal_ip(host: str) -> bool:
    """Resolve *host* and return True if it points to a private / reserved IP."""
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        logger.warning("is_internal_ip: could not resolve %s — treating as internal", host)
        return True

    for family, _, _, _, sockaddr in addrs:
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
            if any(addr in net for net in _PRIVATE_RANGES):
                return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Filename sanitisation (path-traversal prevention)
# ---------------------------------------------------------------------------

# Characters allowed in filenames — everything else is stripped
# Note: hyphen must be placed at the end of the character class to be literal.
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_.-]")


def sanitize_filename(name: str) -> str:
    """Strip path-separator and traversal sequences from *name*."""
    if ".." in name or "/" in name or "\\" in name:
        name = name.replace("..", "").replace("/", "_").replace("\\", "_")
    name = _SAFE_FILENAME_RE.sub("", name)
    # Prevent empty result
    return name if name else "untitled"
