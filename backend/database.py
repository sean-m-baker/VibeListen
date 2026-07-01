from typing import Optional, Generator
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint, event
from sqlmodel import SQLModel, Field, create_engine, Session
from backend.config import SQLITE_DB_PATH

# Setup connection string
sqlite_url = f"sqlite:///{SQLITE_DB_PATH}"

# check_same_thread=False is required for SQLite inside a multi-threaded web server like FastAPI
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


# Enable WAL mode and set a busy timeout for better concurrent read/write performance
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(db_connection, _connection_record):
    cursor = db_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

class Bookmark(SQLModel, table=True):
    """
    Relational DB model representing a read-it-later bookmark.
    Includes state trackers for content cleaning and audio synthesis.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    raindrop_id: Optional[int] = Field(default=None, unique=True, index=True, nullable=True)
    instapaper_id: Optional[int] = Field(default=None, unique=True, index=True, nullable=True)
    service: str = Field(default="raindrop", index=True, nullable=False)
    title: str = Field(nullable=False)
    author: Optional[str] = None
    url: str = Field(nullable=False)
    domain: str = Field(nullable=False)
    clean_text: Optional[str] = None
    audio_filename: Optional[str] = None
    audio_duration: Optional[float] = None  # Duration in seconds
    audio_filesize: Optional[int] = None    # Size in bytes
    status: str = Field(default="pending", index=True)  # pending, parsing, parsing_failed, synthesizing, completed, failed
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generated_at: Optional[datetime] = None


class Setting(SQLModel, table=True):
    """
    Simple key-value store for user-configurable application settings.
    Primary keys are scoped by section and key.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    section: str = Field(default="general", index=True, nullable=False)
    key: str = Field(nullable=False)
    value: str = Field(default="", nullable=False)
    
    # Ensure unique constraint on section + key
    __table_args__ = (UniqueConstraint("section", "key"),)


def get_setting(db: Session, key: str, default: str = "", section: str = "general") -> str:
    """Fetch a setting value by key, returning a default if not found."""
    from sqlalchemy import select
    from backend.auth import decrypt_secret, is_secret_key

    statement = select(Setting).where(Setting.section == section, Setting.key == key)
    result = db.exec(statement).scalars().first()
    if not result:
        return default
    if is_secret_key(key):
        return decrypt_secret(result.value)
    return result.value


def set_setting(db: Session, key: str, value: str, section: str = "general", commit: bool = True) -> Setting:
    """Upsert a setting value by key. Secret values are encrypted at rest."""
    from sqlalchemy import select
    from backend.auth import encrypt_secret, is_secret_key

    if is_secret_key(key) and value:
        value = encrypt_secret(value)

    statement = select(Setting).where(Setting.section == section, Setting.key == key)
    existing = db.exec(statement).scalars().first()
    if existing:
        existing.value = value
        db.add(existing)
        if commit:
            db.commit()
            db.refresh(existing)
        return existing
    new_setting = Setting(section=section, key=key, value=value)
    db.add(new_setting)
    if commit:
        db.commit()
        db.refresh(new_setting)
    return new_setting


def migrate_database() -> None:
    """Run lightweight schema updates on existing database files dynamically."""
    import logging
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError

    db_logger = logging.getLogger("VibeListen.DatabaseMigration")

    db_path = SQLITE_DB_PATH
    if not db_path.exists():
        return

    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            columns = [col["name"] for col in inspector.get_columns("bookmark")]

            if "instapaper_id" not in columns:
                db_logger.info("Database migration: adding 'instapaper_id' column to 'bookmark' table.")
                conn.execute(text("ALTER TABLE bookmark ADD COLUMN instapaper_id INTEGER"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_bookmark_instapaper_id ON bookmark (instapaper_id)"))
                conn.commit()

            if "service" not in columns:
                db_logger.info("Database migration: adding 'service' column to 'bookmark' table.")
                conn.execute(text("ALTER TABLE bookmark ADD COLUMN service VARCHAR"))
                conn.execute(text("UPDATE bookmark SET service = 'raindrop' WHERE service IS NULL"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bookmark_service ON bookmark (service)"))
                conn.commit()

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bookmark_status_added_at ON bookmark (status, added_at DESC)"))
            conn.commit()
    except OperationalError:
        # Table may not exist yet on first run; that's fine
        pass
    except Exception as e:
        db_logger.error(f"Database migration failed: {str(e)}")


def init_db() -> None:
    """Creates the SQLite database and all defined tables."""
    migrate_database()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Dependency injector yielding a database session context."""
    with Session(engine) as session:
        yield session
