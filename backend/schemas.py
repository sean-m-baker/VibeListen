from pydantic import BaseModel, Field

# Known configuration keys grouped by section.
# Any setting not in this allowlist will be rejected.
_ALLOWED_SETTINGS: dict[str, set[str]] = {
    "general": {"sync_service", "max_rss_items", "theme"},
    "raindrop": {"raindrop_token"},
    "instapaper": {
        "instapaper_consumer_key",
        "instapaper_consumer_secret",
        "instapaper_username",
        "instapaper_password",
        "instapaper_oauth_token",
        "instapaper_oauth_token_secret",
    },
    "tts": {
        "tts_engine",
        "tts_voice",
        "audio_bitrate",
        "reference_audio",
    },
}

# Maximum length for any setting value
MAX_SETTING_VALUE_LENGTH = 4096
MAX_SETTING_KEY_LENGTH = 64
MAX_SETTING_SECTION_LENGTH = 32


def validate_setting(section: str, key: str, value: str) -> None:
    """Validate a setting key/value against the allowlist and length limits.

    Raises ``ValueError`` if the setting is not allowed or exceeds limits.
    """
    if len(section) > MAX_SETTING_SECTION_LENGTH:
        raise ValueError(f"Section too long (max {MAX_SETTING_SECTION_LENGTH} chars)")
    if len(key) > MAX_SETTING_KEY_LENGTH:
        raise ValueError(f"Key too long (max {MAX_SETTING_KEY_LENGTH} chars)")
    if len(value) > MAX_SETTING_VALUE_LENGTH:
        raise ValueError(f"Value too long (max {MAX_SETTING_VALUE_LENGTH} chars)")

    section_allowed = _ALLOWED_SETTINGS.get(section)
    if section_allowed is None:
        raise ValueError(f"Unknown section: '{section}'")
    if key not in section_allowed:
        raise ValueError(f"Unknown setting '{key}' in section '{section}'")
