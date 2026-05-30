import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session, SQLModel, create_engine, select
from backend.database import Bookmark
from backend.syncer import sync_raindrops

@pytest.fixture(name="session")
def session_fixture():
    """Provides a temporary, in-memory SQLite database context for testing."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@patch("backend.syncer.requests.get")
@patch("backend.syncer.RAINDROP_TOKEN", "mock_developer_token")
def test_sync_raindrops_successful_import(mock_get, session):
    # 1. Arrange: Setup simulated Raindrop.io JSON response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": True,
        "items": [
            {
                "_id": 99911,
                "title": "Clean Scraped Article",
                "excerpt": "An article detailing software engineering.",
                "link": "https://example.com/clean-article",
                "domain": "example.com",
                "created": "2026-05-22T10:00:00.000Z"
            },
            {
                "_id": 99922,
                "title": "Second Synced Bookmark",
                "excerpt": "A short description of something interesting.",
                "link": "https://example.com/second-article",
                "domain": "example.com",
                "created": "2026-05-22T11:30:00.000Z"
            }
        ]
    }
    mock_get.return_value = mock_response

    # 2. Act: Trigger sync function
    new_bookmarks_count = sync_raindrops(session)

    # 3. Assert: Verify returned counts and database states
    assert new_bookmarks_count == 2
    
    # Query database and verify fields were parsed and saved correctly
    bookmarks = session.exec(select(Bookmark)).all()
    assert len(bookmarks) == 2
    
    # Assert details of first bookmark
    assert bookmarks[0].raindrop_id == 99911
    assert bookmarks[0].title == "Clean Scraped Article"
    assert bookmarks[0].status == "pending"
    assert bookmarks[0].domain == "example.com"
    
    # 4. Act: Attempt a duplicate sync
    # Since the mock returns the same IDs, the duplicate count should be exactly 0
    duplicate_sync_count = sync_raindrops(session)
    assert duplicate_sync_count == 0
