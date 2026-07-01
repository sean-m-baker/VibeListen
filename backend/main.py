import os
import hashlib
import asyncio
import logging
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from sqlmodel import Session, select

from backend.config import BASE_DIR, AUDIO_DIR, AUDIO_CACHE_DIR, MODELS_DIR, REFERENCE_WAV_PATH, SECRET_KEY
from backend.database import init_db, get_session, Bookmark, Setting, get_setting, set_setting
from backend.auth import require_api_key, require_csrf_header, is_secret_key, secret_redactor, sanitize_filename
from backend.schemas import validate_setting
from backend.syncer import sync_bookmarks
from backend.rss_generator import generate_podcast_rss
from backend.tts_engines import list_available_engines

# Setup server logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VibeListen")

app = FastAPI(title="VibeListen", description="Personal Read-it-Later Podcast Server")

# Configure CORS — allow any origin (personal tool, header-based auth)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key", "X-Requested-By"],
    expose_headers=["X-API-Key"],
)

# Rate limiter — keyed by client IP
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# Global handler — catch unhandled exceptions and return a generic response
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ----------------- Static File Routing -----------------

# Serve the main dashboard page at `/`
@app.get("/")
def read_root():
    index_path = BASE_DIR / "frontend" / "index.html"
    if not os.path.exists(index_path):
        return {"message": "Welcome to VibeListen API! Dashboard index.html is not created yet."}
    html = index_path.read_text(encoding="utf-8")
    # Inject API key as a meta tag so the frontend JS can read it
    meta_tag = f'<meta name="api-key" content="{SECRET_KEY}">'
    html = html.replace("</head>", f"  {meta_tag}\n</head>")
    return Response(content=html, media_type="text/html")

# Mount audio storage directory under `/audio` to serve synthesized MP3 enclosures
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# ----------------- Transcoded Audio for RSS -----------------

@app.get("/rss-audio/{filename:path}")
async def serve_rss_audio(filename: str):
    """Serve pre-transcoded MP3 audio for podcast app compatibility.

    Transcoding is done by the background worker after synthesis completes,
    so this endpoint only serves already-cached files — it never spawns
    ffmpeg dynamically (prevents unauthenticated DoS via CPU exhaustion).
    """
    if not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only MP3 output is supported")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    mp3_path = (AUDIO_CACHE_DIR / filename).resolve()
    if not str(mp3_path).startswith(str(AUDIO_CACHE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid cache path")
    if not mp3_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(mp3_path, media_type="audio/mpeg", filename=filename)


# ----------------- API Endpoints -----------------

@app.get("/api/bookmarks", response_model=List[Bookmark])
def list_bookmarks(db: Session = Depends(get_session), _auth: None = Depends(require_api_key)):
    """Lists all bookmarks in the SQLite database, newest first."""
    statement = select(Bookmark).order_by(Bookmark.added_at.desc())
    return db.exec(statement).all()

@app.delete("/api/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int, db: Session = Depends(get_session), _auth: None = Depends(require_api_key)):
    """Deletes a bookmark and its associated audio files from disk."""
    bookmark = db.get(Bookmark, bookmark_id)
    if not bookmark:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    # Remove audio file from disk if it exists
    if bookmark.audio_filename:
        safe_name = sanitize_filename(bookmark.audio_filename)
        if safe_name != bookmark.audio_filename:
            logger.warning(
                f"Sanitized audio_filename for bookmark {bookmark_id}: "
                f"'{bookmark.audio_filename}' -> '{safe_name}'"
            )
        audio_path = (AUDIO_DIR / safe_name).resolve()
        if not str(audio_path).startswith(str(AUDIO_DIR.resolve())):
            raise HTTPException(status_code=400, detail="Invalid audio filename")
        if audio_path.exists():
            audio_path.unlink()
            logger.info(f"Deleted audio file: {audio_path}")

        # Remove transcoded MP3 cache if it exists
        if safe_name.endswith(".wav"):
            mp3_name = safe_name.replace(".wav", ".mp3")
            mp3_path = (AUDIO_CACHE_DIR / mp3_name).resolve()
            if not str(mp3_path).startswith(str(AUDIO_CACHE_DIR.resolve())):
                raise HTTPException(status_code=400, detail="Invalid cache filename")
            if mp3_path.exists():
                mp3_path.unlink()
                logger.info(f"Deleted cached MP3: {mp3_path}")

    db.delete(bookmark)
    db.commit()
    logger.info(f"Deleted bookmark ID {bookmark_id}: '{bookmark.title}'")
    return {"status": "success", "message": f"Bookmark '{bookmark.title}' deleted."}

@app.post("/api/sync")
@limiter.limit("5/minute")
def trigger_sync(request: Request, db: Session = Depends(get_session), _auth: None = Depends(require_api_key), _csrf: None = Depends(require_csrf_header)):
    """Triggers synchronizing newest bookmarks from configured read-it-later services."""
    try:
        new_count = sync_bookmarks(db)
        return {"status": "success", "new_bookmarks_count": new_count}
    except Exception as e:
        logger.exception("Sync failed")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/generate/{bookmark_id}")
@limiter.limit("30/minute")
def trigger_generation(
    request: Request,
    bookmark_id: int, 
    db: Session = Depends(get_session),
    _auth: None = Depends(require_api_key),
    _csrf: None = Depends(require_csrf_header),
):
    """Queue a bookmark for processing by the standalone background worker."""
    bookmark = db.get(Bookmark, bookmark_id)
    if not bookmark:
        raise HTTPException(status_code=404, detail="Bookmark not found")
        
    if bookmark.status in ["queued", "processing", "parsing", "synthesizing"]:
        return {"status": "already_running", "message": "Bookmark is already in queue or being processed."}
        
    bookmark.status = "queued"
    db.add(bookmark)
    db.commit()
    
    return {"status": "queued", "message": "Bookmark added to worker queue."}

@app.get("/rss.xml")
def get_rss_feed(request: Request, db: Session = Depends(get_session)):
    """Generates and serves the dynamic Podcast RSS XML feed with caching support."""
    max_items = int(get_setting(db, "max_rss_items", "100", section="general"))
    bitrate = get_setting(db, "audio_bitrate", "64", section="tts")

    statement = (
        select(Bookmark)
        .where(Bookmark.status == "completed")
        .order_by(Bookmark.added_at.desc())
        .limit(max_items)
    )
    completed_bookmarks = db.exec(statement).all()

    # Compute ETag from the most recent bookmark's generated_at timestamp
    etag = None
    if completed_bookmarks:
        latest = completed_bookmarks[0].generated_at or completed_bookmarks[0].added_at
        etag = hashlib.md5(str(latest.timestamp()).encode()).hexdigest()

    # Return 304 Not Modified if ETag matches
    if etag and request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    rss_xml = generate_podcast_rss(completed_bookmarks, bitrate=bitrate)
    headers = {"ETag": etag} if etag else {}
    return Response(content=rss_xml, media_type="application/xml", headers=headers)


# ----------------- Settings API -----------------

@app.get("/api/settings")
def get_all_settings(db: Session = Depends(get_session), _auth: None = Depends(require_api_key)):
    """Returns all user-configurable settings grouped by section."""
    settings = db.exec(select(Setting)).all()
    result: Dict[str, Dict[str, str]] = {}
    for s in settings:
        if s.section not in result:
            result[s.section] = {}
        result[s.section][s.key] = secret_redactor(s.value) if is_secret_key(s.key) else s.value
    return result


@app.post("/api/settings")
@limiter.limit("30/minute")
def update_setting(
    request: Request,
    key: str = Form(...),
    value: str = Form(default=""),
    section: str = Form("general"),
    db: Session = Depends(get_session),
    _auth: None = Depends(require_api_key),
    _csrf: None = Depends(require_csrf_header),
):
    """Create or update a single setting."""
    validate_setting(section, key, value)
    setting = set_setting(db, key, value, section)
    logger.info(f"Setting updated: [{section}] {key} = {value}")
    return {"status": "success", "section": setting.section, "key": setting.key, "value": setting.value}


@app.post("/api/settings/bulk")
@limiter.limit("30/minute")
def bulk_update_settings(
    request: Request,
    payload: Dict[str, Dict[str, str]],
    db: Session = Depends(get_session),
    _auth: None = Depends(require_api_key),
    _csrf: None = Depends(require_csrf_header),
):
    """Update multiple settings in a single request and transaction.
    
    Payload format: {"section": {"key": "value", ...}, ...}
    """
    for section, keys in payload.items():
        for key, value in keys.items():
            validate_setting(section, key, value)
            set_setting(db, key, value, section, commit=False)
    db.commit()
    logger.info(f"Bulk settings update: {sum(len(v) for v in payload.values())} values")
    return {"status": "success"}


# ----------------- TTS Engine API -----------------

@app.get("/api/tts/engines")
def get_tts_engines(_auth: None = Depends(require_api_key)):
    """Lists all registered TTS engines and their installation status."""
    return {"engines": list_available_engines()}


@app.get("/api/tts/voices/{engine}")
def get_voices_for_engine(engine: str, _auth: None = Depends(require_api_key)):
    """Returns available voice options for a given TTS engine."""
    engine = engine.lower().strip()
    if engine == "edge":
        return {
            "voices": [
                {"id": "en-US-GuyNeural", "name": "Guy (US English)"},
                {"id": "en-US-JennyNeural", "name": "Jenny (US English)"},
                {"id": "en-GB-RyanNeural", "name": "Ryan (UK English)"},
                {"id": "en-GB-SoniaNeural", "name": "Sonia (UK English)"},
                {"id": "en-AU-WillNeural", "name": "Will (Australian English)"},
                {"id": "en-CA-LiamNeural", "name": "Liam (Canadian English)"},
            ]
        }
    elif engine == "piper":
        return {
            "voices": [
                {"id": "en_US-lessac-medium", "name": "Lessac Medium (US English)"},
                {"id": "en_US-ryan-high", "name": "Ryan High (US English)"},
                {"id": "en_GB-southern_english_female-medium", "name": "Southern English Female (UK)"},
                {"id": "en_GB-northern_english_male-medium", "name": "Northern English Male (UK)"},
            ]
        }
    elif engine == "pocket":
        return {
            "voices": [
                {"id": "default", "name": "Default CALM Voice"},
                {"id": "cloned", "name": "Cloned Reference Voice"},
            ]
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")


MAX_REFERENCE_UPLOAD = 10 * 1024 * 1024  # 10 MB


@app.post("/api/tts/reference")
@limiter.limit("5/minute")
async def upload_reference_audio(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    _auth: None = Depends(require_api_key),
    _csrf: None = Depends(require_csrf_header),
):
    """Upload a reference WAV file for voice cloning (Pocket TTS)."""
    if not file.filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are supported for reference audio.")

    if file.size and file.size > MAX_REFERENCE_UPLOAD:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_REFERENCE_UPLOAD // (1024 * 1024)} MB.",
        )

    import wave
    import io

    try:
        contents = await file.read()
        if len(contents) > MAX_REFERENCE_UPLOAD:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_REFERENCE_UPLOAD // (1024 * 1024)} MB.",
            )

        # Validate RIFF WAV header before parsing the full structure
        if contents[:4] != b"RIFF":
            raise HTTPException(status_code=400, detail="File is not a valid WAV (missing RIFF header).")

        with wave.open(io.BytesIO(contents), "rb") as w:
            if w.getnchannels() != 1:
                raise HTTPException(status_code=400, detail="Reference audio must be mono (1 channel).")
            if w.getframerate() != 24000:
                raise HTTPException(status_code=400, detail="Reference audio must be 24000 Hz sample rate.")
            if w.getsampwidth() != 2:
                raise HTTPException(status_code=400, detail="Reference audio must be 16-bit.")
            if w.getnframes() > 10_000_000:
                raise HTTPException(status_code=400, detail="Reference audio has too many frames.")
    except wave.Error:
        raise HTTPException(status_code=400, detail="Invalid or corrupted WAV file.")

    try:
        REFERENCE_WAV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REFERENCE_WAV_PATH, "wb") as f:
            f.write(contents)
        
        set_setting(db, "reference_audio", str(REFERENCE_WAV_PATH), section="tts")
        
        logger.info(f"Reference audio uploaded: {REFERENCE_WAV_PATH} ({len(contents)} bytes)")
        return {
            "status": "success",
            "message": "Reference audio uploaded successfully.",
            "path": str(REFERENCE_WAV_PATH),
            "size": len(contents),
        }
    except Exception as e:
        logger.exception("Failed to upload reference audio")
        raise HTTPException(status_code=500, detail="Internal server error")


# Mount general static assets (js, css, images) under `/frontend`
app.mount("/frontend", StaticFiles(directory=str(BASE_DIR / "frontend")), name="frontend")
