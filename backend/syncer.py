import logging
import os
import requests
import urllib.parse
from datetime import datetime, timezone

from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config import RAINDROP_TOKEN
from backend.database import Bookmark, get_setting, set_setting


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
    
    db_token = get_setting(session, "raindrop_token", default="", section="raindrop")
    token = (db_token or RAINDROP_TOKEN).strip()
    
    if not token:
        logger.error("Raindrop API token is not configured or empty.")
        raise ValueError("Raindrop API token is not configured.")

    logger.info(f"Raindrop API token configured (length: {len(token)} chars)")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    params = {
        "perpage": limit,
        "sort": "-created"  # Newest bookmarks first
    }

    logger.info(f"Sending GET request to Raindrop API: {RAINDROP_API_URL}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _raindrop_api_call() -> requests.Response:
        resp = requests.get(RAINDROP_API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp

    try:
        response = _raindrop_api_call()
        logger.info(f"Raindrop API responded with HTTP Status Code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"HTTP request failed: {str(e)}")
        if "401" in str(e):
            raise RuntimeError("Raindrop API token is Unauthorized (401). Please verify your token in the .env file.")
        raise RuntimeError(f"Failed to connect to Raindrop API: {e}")

    data = response.json()
    if not data.get("result", False):
        logger.error(f"Raindrop API returned failed result flag. Response payload: {data}")
        raise RuntimeError("Raindrop API returned an unsuccessful result status.")

    items = data.get("items", [])
    logger.info(f"Successfully retrieved {len(items)} bookmarks from Raindrop account.")

    # Single query: fetch all existing raindrop IDs to avoid N+1 lookups
    existing_raindrop_ids = set(
        session.exec(select(Bookmark.raindrop_id).where(Bookmark.raindrop_id.isnot(None)))
    )

    new_bookmarks_count = 0

    for item in items:
        raindrop_id = item.get("_id")
        if not raindrop_id:
            logger.warning("Skipping parsed bookmark because it lacks a valid '_id'.")
            continue
            
        if raindrop_id in existing_raindrop_ids:
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


def get_instapaper_oauth_tokens(
    consumer_key: str, consumer_secret: str, username: str, password: str
) -> tuple[str, str]:
    """
    Exchanges Instapaper username & password credentials for OAuth 1.0a access tokens
    using the Instapaper xAuth API endpoint.
    """
    from requests_oauthlib import OAuth1
    url = "https://www.instapaper.com/api/1/oauth/access_token"
    auth = OAuth1(consumer_key, client_secret=consumer_secret)
    data = {
        "x_auth_username": username,
        "x_auth_password": password,
        "x_auth_mode": "client_auth"
    }
    logger.info("Sending xAuth request to Instapaper...")
    response = requests.post(url, auth=auth, data=data, timeout=10)
    
    if response.status_code == 401:
        logger.error("❌ HTTP 401 Unauthorized: Invalid Instapaper credentials or API consumer keys.")
        raise ValueError("Invalid Instapaper credentials or consumer keys.")
        
    response.raise_for_status()
    
    # Parse responses which are returned as query string parameters
    params = urllib.parse.parse_qs(response.text)
    oauth_token = params.get("oauth_token", [None])[0]
    oauth_token_secret = params.get("oauth_token_secret", [None])[0]
    
    if not oauth_token or not oauth_token_secret:
        logger.error(f"Failed to parse OAuth tokens from response body: {response.text}")
        raise ValueError("Invalid OAuth response payload from Instapaper.")
        
    return oauth_token, oauth_token_secret


def sync_instapaper(session: Session, limit: int = 50) -> int:
    """
    Polls Instapaper for the latest bookmarks using OAuth 1.0a, parses them,
    and saves any new entries to the database with a 'pending' status.
    
    Returns the count of newly added bookmarks.
    """
    logger.info("Initializing Instapaper sync process...")
    
    # 1. Load consumer credentials (DB first, fallback to env)
    consumer_key = get_setting(session, "instapaper_consumer_key", default=os.getenv("INSTAPAPER_CONSUMER_KEY", ""), section="instapaper").strip()
    consumer_secret = get_setting(session, "instapaper_consumer_secret", default=os.getenv("INSTAPAPER_CONSUMER_SECRET", ""), section="instapaper").strip()
    
    if not consumer_key or not consumer_secret:
        logger.error("Instapaper consumer credentials are not configured.")
        raise ValueError("Instapaper Consumer Key or Secret is not configured.")
        
    # 2. Check if we already have oauth token / secret saved in database
    oauth_token = get_setting(session, "instapaper_oauth_token", default=os.getenv("INSTAPAPER_OAUTH_TOKEN", ""), section="instapaper").strip()
    oauth_token_secret = get_setting(session, "instapaper_oauth_token_secret", default=os.getenv("INSTAPAPER_OAUTH_TOKEN_SECRET", ""), section="instapaper").strip()
    
    if not oauth_token or not oauth_token_secret:
        # Require username/password to retrieve tokens
        username = get_setting(session, "instapaper_username", default=os.getenv("INSTAPAPER_USERNAME", ""), section="instapaper").strip()
        password = get_setting(session, "instapaper_password", default=os.getenv("INSTAPAPER_PASSWORD", ""), section="instapaper").strip()
        
        if not username or not password:
            logger.error("Instapaper credentials or OAuth tokens are missing.")
            raise ValueError("Instapaper credentials are not configured.")
            
        logger.info("No stored OAuth tokens. Performing xAuth login...")
        oauth_token, oauth_token_secret = get_instapaper_oauth_tokens(
            consumer_key, consumer_secret, username, password
        )
        
        # Save tokens in database settings to cache them
        set_setting(session, "instapaper_oauth_token", oauth_token, section="instapaper")
        set_setting(session, "instapaper_oauth_token_secret", oauth_token_secret, section="instapaper")
        logger.info("Successfully fetched and saved Instapaper OAuth tokens.")
        
    # 3. Request bookmarks list from Instapaper API
    # Endpoints use OAuth1 authorization headers
    from requests_oauthlib import OAuth1
    auth = OAuth1(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret
    )
    
    url = "https://www.instapaper.com/api/1/bookmarks/list"
    data = {"limit": limit}
    
    logger.info(f"Sending POST request to Instapaper API: {url}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _instapaper_api_call() -> requests.Response:
        resp = requests.post(url, auth=auth, data=data, timeout=10)
        resp.raise_for_status()
        return resp

    try:
        response = _instapaper_api_call()
        logger.info(f"Instapaper API responded with HTTP Status Code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"HTTP request failed: {str(e)}")
        if "401" in str(e):
            logger.error("Instapaper tokens invalid. Clearing stored credentials to trigger re-auth.")
            set_setting(session, "instapaper_oauth_token", "", section="instapaper")
            set_setting(session, "instapaper_oauth_token_secret", "", section="instapaper")
            raise RuntimeError("Instapaper API returned Unauthorized (401). Cached tokens cleared.")
        raise RuntimeError(f"Failed to connect to Instapaper API: {e}")
        
    try:
        payload = response.json()
    except Exception as e:
        logger.error(f"Failed to parse Instapaper JSON response: {response.text}")
        raise RuntimeError("Invalid JSON response from Instapaper API.") from e
        
    # Instapaper API returns list containing a mixture of objects.
    # Bookmark elements have type = 'bookmark'.

    # Single query: fetch all existing instapaper IDs to avoid N+1 lookups
    existing_instapaper_ids = set(
        session.exec(select(Bookmark.instapaper_id).where(Bookmark.instapaper_id.isnot(None)))
    )

    new_bookmarks_count = 0
    
    for item in payload:
        if isinstance(item, dict) and item.get("type") == "bookmark":
            bookmark_id = item.get("bookmark_id")
            if not bookmark_id:
                continue
                
            if bookmark_id in existing_instapaper_ids:
                continue
                
            # Parse added_at (Unix timestamp)
            time_val = item.get("time")
            if time_val:
                try:
                    added_at = datetime.fromtimestamp(float(time_val), timezone.utc)
                except Exception:
                    added_at = datetime.now(timezone.utc)
            else:
                added_at = datetime.now(timezone.utc)
                
            # Extract domain from URL
            link = item.get("url", "")
            try:
                parsed_url = urllib.parse.urlparse(link)
                domain = parsed_url.netloc or "unknown.com"
            except Exception:
                domain = "unknown.com"
                
            # Create new bookmark
            new_bookmark = Bookmark(
                instapaper_id=bookmark_id,
                service="instapaper",
                title=item.get("title", "Untitled Bookmark"),
                author=item.get("description", "")[:255] or "Unknown",
                url=link,
                domain=domain,
                status="pending",
                added_at=added_at
            )
            
            logger.info(f"➕ Importing NEW Instapaper bookmark: ID {bookmark_id} | '{new_bookmark.title}' from {new_bookmark.domain}")
            session.add(new_bookmark)
            new_bookmarks_count += 1
            
    if new_bookmarks_count > 0:
        session.commit()
        logger.info(f"Database transaction committed. Successfully imported {new_bookmarks_count} new Instapaper bookmarks.")
    else:
        logger.info("Instapaper sync complete. No new bookmarks were found to import.")
        
    return new_bookmarks_count


def sync_bookmarks(session: Session, limit: int = 50) -> int:
    """
    Unified sync dispatcher. Checks configured settings and runs syncs
    for all active/enabled read-it-later integrations.
    
    Returns total count of new bookmarks successfully imported.
    """
    total_new = 0
    errors = []
    
    # 1. Determine selected sync service
    sync_service = get_setting(session, "sync_service", default="both", section="general").strip().lower()
    
    # 2. Check and run Raindrop.io sync
    if sync_service in ["raindrop", "both"]:
        # Verify if token or env var is configured
        db_token = get_setting(session, "raindrop_token", default="", section="raindrop").strip()
        if db_token or RAINDROP_TOKEN:
            try:
                total_new += sync_raindrops(session, limit)
            except Exception as e:
                logger.error(f"Sync dispatcher: Raindrop sync failed: {e}")
                errors.append(f"Raindrop sync: {e}")
                
    # 3. Check and run Instapaper sync
    if sync_service in ["instapaper", "both"]:
        consumer_key = get_setting(session, "instapaper_consumer_key", default=os.getenv("INSTAPAPER_CONSUMER_KEY", ""), section="instapaper").strip()
        if consumer_key:
            try:
                total_new += sync_instapaper(session, limit)
            except Exception as e:
                logger.error(f"Sync dispatcher: Instapaper sync failed: {e}")
                errors.append(f"Instapaper sync: {e}")
                
    if errors:
        # If both failed, or one failed and the other wasn't run/configured, raise an error
        # otherwise we still return the synced count.
        if len(errors) == 1 and total_new == 0:
            raise RuntimeError(errors[0])
        elif len(errors) > 1 and total_new == 0:
            raise RuntimeError("; ".join(errors))
            
    return total_new
