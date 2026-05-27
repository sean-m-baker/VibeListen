from typing import Optional, Generator
<<<<<<< HEAD
from datetime import datetime, timezone
=======
from datetime import datetime
>>>>>>> df01a4e (feat: add database-backed application settings and TTS engine/voice configuration support)
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
    raindrop_id: int = Field(unique=True, index=True, nullable=False)
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
    statement = select(Setting).where(Setting.section == section, Setting.key == key)
    result = db.exec(statement).scalars().first()
    return result.value if result else default


def set_setting(db: Session, key: str, value: str, section: str = "general") -> Setting:
    """Upsert a setting value by key."""
    from sqlalchemy import select
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


def init_db() -> None:
    """Creates the SQLite database and all defined tables."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Dependency injector yielding a database session context."""
    with Session(engine) as session:
        yield session
