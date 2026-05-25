from typing import Optional, Generator
from datetime import datetime
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
    added_at: datetime = Field(default_factory=datetime.utcnow)
    generated_at: Optional[datetime] = None

def init_db() -> None:
    """Creates the SQLite database and all defined tables."""
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    """Dependency injector yielding a database session context."""
    with Session(engine) as session:
        yield session
