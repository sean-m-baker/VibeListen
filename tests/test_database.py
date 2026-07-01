import pytest
from sqlmodel import Session, SQLModel, create_engine

from backend.database import Setting, get_setting, set_setting


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestSecretEncryption:
    """Secret values should be encrypted at rest, transparently decrypted on read."""

    def test_secret_encrypted_at_rest(self, session):
        """A secret key's value should be ciphertext in the DB, not plaintext."""
        set_setting(session, "raindrop_token", "super-secret-token", section="raindrop")
        from sqlalchemy import select
        stmt = select(Setting).where(Setting.section == "raindrop", Setting.key == "raindrop_token")
        stored = session.exec(stmt).scalars().one()
        assert stored.value != "super-secret-token"
        assert not stored.value.startswith("super")

    def test_secret_decrypted_on_read(self, session):
        """get_setting should return the original plaintext for secret keys."""
        set_setting(session, "instapaper_password", "my-password", section="instapaper")
        result = get_setting(session, "instapaper_password", section="instapaper")
        assert result == "my-password"

    def test_non_secret_stored_as_plaintext(self, session):
        """Non-secret keys should be stored as-is."""
        set_setting(session, "tts_engine", "piper", section="tts")
        from sqlalchemy import select
        stmt = select(Setting).where(Setting.section == "tts", Setting.key == "tts_engine")
        stored = session.exec(stmt).scalars().one()
        assert stored.value == "piper"

    def test_non_secret_read_returns_plaintext(self, session):
        set_setting(session, "max_rss_items", "50", section="general")
        assert get_setting(session, "max_rss_items", section="general") == "50"

    def test_pre_migration_plaintext_still_readable(self, session):
        """Values stored before encryption feature (plaintext) should still be readable."""
        from sqlalchemy import select
        # Insert a setting directly (bypassing encryption)
        setting = Setting(section="instapaper", key="instapaper_password", value="old-plaintext")
        session.add(setting)
        session.commit()

        result = get_setting(session, "instapaper_password", section="instapaper")
        assert result == "old-plaintext"

    def test_secret_default_returned_when_missing(self, session):
        result = get_setting(session, "nonexistent_key", default="fallback", section="general")
        assert result == "fallback"

    def test_empty_secret_not_encrypted(self, session):
        """Empty string values for secret keys should stay empty (not crash)."""
        set_setting(session, "raindrop_token", "", section="raindrop")
        result = get_setting(session, "raindrop_token", section="raindrop")
        assert result == ""

    def test_multiple_secrets_independent(self, session):
        set_setting(session, "token_a", "value-a", section="test")
        set_setting(session, "token_b", "value-b", section="test")
        assert get_setting(session, "token_a", section="test") == "value-a"
        assert get_setting(session, "token_b", section="test") == "value-b"
