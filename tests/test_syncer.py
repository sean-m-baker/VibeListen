import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session, SQLModel, create_engine, select
from backend.database import Bookmark, set_setting
from backend.syncer import (
    sync_raindrops,
    sync_instapaper,
    get_instapaper_oauth_tokens,
    sync_bookmarks,
)

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


@patch("backend.syncer.requests.post")
def test_get_instapaper_oauth_tokens_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "oauth_token=test_token_123&oauth_token_secret=test_secret_456"
    mock_post.return_value = mock_response

    token, secret = get_instapaper_oauth_tokens("key", "secret", "user", "pass")
    assert token == "test_token_123"
    assert secret == "test_secret_456"
    mock_post.assert_called_once()


@patch("backend.syncer.requests.post")
def test_get_instapaper_oauth_tokens_unauthorized(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_post.return_value = mock_response

    with pytest.raises(ValueError, match="Invalid Instapaper credentials"):
        get_instapaper_oauth_tokens("key", "secret", "user", "pass")


@patch("backend.syncer.requests.post")
def test_sync_instapaper_successful_import(mock_post, session):
    # Setup settings
    set_setting(session, "instapaper_consumer_key", "key", section="instapaper")
    set_setting(session, "instapaper_consumer_secret", "secret", section="instapaper")
    set_setting(session, "instapaper_oauth_token", "token", section="instapaper")
    set_setting(session, "instapaper_oauth_token_secret", "token_secret", section="instapaper")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"type": "user", "username": "test_user"},
        {
            "type": "bookmark",
            "bookmark_id": 112233,
            "title": "Instapaper Title",
            "description": "An Instapaper excerpt.",
            "url": "https://example.com/instapaper-article",
            "time": 1774872000
        }
    ]
    mock_post.return_value = mock_response

    new_count = sync_instapaper(session)
    assert new_count == 1

    bookmarks = session.exec(select(Bookmark)).all()
    assert len(bookmarks) == 1
    assert bookmarks[0].instapaper_id == 112233
    assert bookmarks[0].title == "Instapaper Title"
    assert bookmarks[0].domain == "example.com"
    assert bookmarks[0].service == "instapaper"


@patch("backend.syncer.requests.post")
def test_sync_instapaper_trigger_xauth_flow(mock_post, session):
    # Setup consumer credentials and username/password, but no OAuth tokens
    set_setting(session, "instapaper_consumer_key", "key", section="instapaper")
    set_setting(session, "instapaper_consumer_secret", "secret", section="instapaper")
    set_setting(session, "instapaper_username", "user", section="instapaper")
    set_setting(session, "instapaper_password", "pass", section="instapaper")

    # The first requests.post will be the xAuth token retrieval.
    # The second requests.post will be the bookmarks retrieval.
    mock_response_xauth = MagicMock()
    mock_response_xauth.status_code = 200
    mock_response_xauth.text = "oauth_token=token123&oauth_token_secret=secret123"

    mock_response_list = MagicMock()
    mock_response_list.status_code = 200
    mock_response_list.json.return_value = [
        {
            "type": "bookmark",
            "bookmark_id": 445566,
            "title": "xAuth Title",
            "url": "https://example.com/xauth-article"
        }
    ]

    mock_post.side_effect = [mock_response_xauth, mock_response_list]

    new_count = sync_instapaper(session)
    assert new_count == 1

    bookmarks = session.exec(select(Bookmark)).all()
    assert len(bookmarks) == 1
    assert bookmarks[0].instapaper_id == 445566
    assert bookmarks[0].title == "xAuth Title"


@patch("backend.syncer.sync_raindrops")
@patch("backend.syncer.sync_instapaper")
def test_sync_bookmarks_dispatcher(mock_sync_instapaper, mock_sync_raindrops, session):
    mock_sync_raindrops.return_value = 2
    mock_sync_instapaper.return_value = 3

    # Configure sync_service to both
    set_setting(session, "sync_service", "both", section="general")

    # Configure mock credentials to trigger both
    set_setting(session, "raindrop_token", "r_token", section="raindrop")
    set_setting(session, "instapaper_consumer_key", "i_key", section="instapaper")

    total = sync_bookmarks(session)
    assert total == 5
    mock_sync_raindrops.assert_called_once_with(session, 50)
    mock_sync_instapaper.assert_called_once_with(session, 50)
