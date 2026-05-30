import logging
import requests
from datetime import datetime, timezone
from sqlmodel import Session, select
from backend.config import RAINDROP_TOKEN
from backend.database import Bookmark

# Configure logger for the syncer module
logger = logging.getLogger("VibeListen.Syncer")

# Raindrop API base endpoints
RAINDROP_API_URL = "https://api.raindrop.io/rest/v1/raindrops/0"

def sync_raindrops(session: Session, limit: int = 50) -> int:
    """
    Polls Raindrop.io for the latest bookmarks, parses them, and saves
    any new entries to the database with a 'pending' status.
    
    Returns the count of newly added bookmarks.
    """
    logger.info("Initializing Raindrop.io sync process...")
    
    if not RAINDROP_TOKEN:
        logger.error("RAINDROP_TOKEN environment variable is not configured or empty.")
        raise ValueError("RAINDROP_TOKEN is not configured. Please add it to your .env file.")

    # Securely print a masked preview of the key to inspect loading issues
    clean_token = RAINDROP_TOKEN.strip()
    masked_token = clean_token[:6] + "..." + clean_token[-4:] if len(clean_token) > 10 else "[TOO_SHORT]"
    logger.info(f"API Token loaded successfully. Length: {len(RAINDROP_TOKEN)} chars (Masked preview: {masked_token})")
    
    if len(RAINDROP_TOKEN) != len(clean_token):
        logger.warning("⚠️ Warning: Your RAINDROP_TOKEN in .env has trailing or leading whitespaces. We will strip them for this request.")

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json"
    }
    
    params = {
        "perpage": limit,
        "sort": "-created"  # Newest bookmarks first
    }

    logger.info(f"Sending GET request to Raindrop API: {RAINDROP_API_URL}")
    try:
        response = requests.get(RAINDROP_API_URL, headers=headers, params=params, timeout=10)
        logger.info(f"Raindrop API responded with HTTP Status Code: {response.status_code}")
        
        if response.status_code == 401:
            logger.error("❌ HTTP 401 Unauthorized: The Raindrop API token is invalid or expired. Check your .env file.")
            raise RuntimeError("Raindrop API token is Unauthorized (401). Please verify your token in the .env file.")
            
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"HTTP request failed: {str(e)}")
        raise RuntimeError(f"Failed to connect to Raindrop API: {e}")

    data = response.json()
    if not data.get("result", False):
        logger.error(f"Raindrop API returned failed result flag. Response payload: {data}")
        raise RuntimeError("Raindrop API returned an unsuccessful result status.")

    items = data.get("items", [])
    logger.info(f"Successfully retrieved {len(items)} bookmarks from Raindrop account.")
    new_bookmarks_count = 0

    for item in items:
        raindrop_id = item.get("_id")
        if not raindrop_id:
            logger.warning("Skipping parsed bookmark because it lacks a valid '_id'.")
            continue
            
        # Check if this bookmark is already imported
        statement = select(Bookmark).where(Bookmark.raindrop_id == raindrop_id)
        existing = session.exec(statement).first()
        if existing:
            logger.debug(f"Bookmark ID {raindrop_id} ('{item.get('title')}') already exists in SQLite. Skipping.")
            continue  # Already in database, skip
            
        # Parse created datetime (e.g. '2026-05-22T17:11:00.000Z')
        created_str = item.get("created", "")
        try:
            # Strip timezone representation and parse
            cleaned_t = created_str.replace("Z", "")
            if "." in cleaned_t:
                cleaned_t = cleaned_t.split(".")[0]
            added_at = datetime.fromisoformat(cleaned_t)
        except Exception:
            added_at = datetime.now(timezone.utc)

        # Create new bookmark entry
        new_bookmark = Bookmark(
            raindrop_id=raindrop_id,
            title=item.get("title", "Untitled Bookmark"),
            author=item.get("excerpt", "")[:255] or item.get("note", "")[:255] or "Unknown",
            url=item.get("link", ""),
            domain=item.get("domain", "unknown.com"),
            status="pending",
            added_at=added_at
        )
        
        logger.info(f"➕ Importing NEW bookmark: ID {raindrop_id} | '{new_bookmark.title}' from {new_bookmark.domain}")
        session.add(new_bookmark)
        new_bookmarks_count += 1

    if new_bookmarks_count > 0:
        session.commit()
        logger.info(f"Database transaction committed. Successfully imported {new_bookmarks_count} new bookmarks.")
    else:
        logger.info("Sync complete. No new bookmarks were found to import.")

    return new_bookmarks_count
