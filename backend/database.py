from typing import Optional, Generator
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, create_engine, Session
from backend.config import SQLITE_DB_PATH

# Setup connection string
sqlite_url = f"sqlite:///{SQLITE_DB_PATH}"

# check_same_thread=False is required for SQLite inside a multi-threaded web server like FastAPI
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

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
    status: str = Field(default="pending")  # pending, parsing, parsing_failed, synthesizing, completed, failed
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


def set_setting(db: Session, key: str, value: str, section: str = "general") -> Setting:
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
        db.commit()
        db.refresh(existing)
        return existing
    new_setting = Setting(section=section, key=key, value=value)
    db.add(new_setting)
    db.commit()
    db.refresh(new_setting)
    return new_setting


def migrate_database() -> None:
    """Run lightweight schema updates on existing database files dynamically."""
    import sqlite3
    import logging
    db_logger = logging.getLogger("VibeListen.DatabaseMigration")
    
    # Simple relative/absolute config fallback
    try:
        from backend.config import SQLITE_DB_PATH
    except ImportError:
        from config import SQLITE_DB_PATH

    db_path = SQLITE_DB_PATH
    if not db_path.exists():
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check existing columns in the bookmark table
        cursor.execute("PRAGMA table_info(bookmark)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add instapaper_id column if missing
        if "instapaper_id" not in columns:
            db_logger.info("Database migration: adding 'instapaper_id' column to 'bookmark' table.")
            cursor.execute("ALTER TABLE bookmark ADD COLUMN instapaper_id INTEGER")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_bookmark_instapaper_id ON bookmark (instapaper_id)")
            conn.commit()
            
        # Add service column if missing
        if "service" not in columns:
            db_logger.info("Database migration: adding 'service' column to 'bookmark' table.")
            cursor.execute("ALTER TABLE bookmark ADD COLUMN service VARCHAR")
            # Set default service to raindrop for existing rows
            cursor.execute("UPDATE bookmark SET service = 'raindrop' WHERE service IS NULL")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_bookmark_service ON bookmark (service)")
            conn.commit()
            
        # Composite index for RSS feed query (status + recency)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bookmark_status_added_at ON bookmark (status, added_at DESC)")
        conn.commit()
        
        conn.close()
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
