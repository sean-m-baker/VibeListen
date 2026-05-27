import os
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Response, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from backend.config import BASE_DIR, AUDIO_DIR, MODELS_DIR, REFERENCE_WAV_PATH
from backend.database import init_db, get_session, Bookmark, Setting, get_setting, set_setting
from backend.syncer import sync_raindrops
from backend.rss_generator import generate_podcast_rss
from backend.tts_engines import list_available_engines

# Setup server logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PodRead")

app = FastAPI(title="PodRead", description="Personal Read-it-Later Podcast Server")

# Configure CORS so dashboard can easily communicate with API from any client host
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize SQLite database on boot
@app.on_event("startup")
def on_startup():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully.")
    
    # Ensure frontend directories are ready
    os.makedirs(BASE_DIR / "frontend", exist_ok=True)

# ----------------- Static File Routing -----------------

# Serve the main dashboard page at `/`
@app.get("/")
def read_root():
    index_path = BASE_DIR / "frontend" / "index.html"
    if not os.path.exists(index_path):
        return {"message": "Welcome to PodRead API! Dashboard index.html is not created yet."}
    return FileResponse(index_path)

# Mount audio storage directory under `/audio` to serve synthesized MP3 enclosures
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# ----------------- API Endpoints -----------------

@app.get("/api/bookmarks", response_model=List[Bookmark])
def list_bookmarks(db: Session = Depends(get_session)):
    """Lists all bookmarks in the SQLite database, newest first."""
    statement = select(Bookmark).order_by(Bookmark.added_at.desc())
    return db.exec(statement).all()

@app.post("/api/sync")
def trigger_sync(db: Session = Depends(get_session)):
    """Triggers synchronizing newest bookmarks from Raindrop.io as a background worker task."""
    try:
        new_count = sync_raindrops(db)
        return {"status": "success", "new_bookmarks_count": new_count}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate/{bookmark_id}")
def trigger_generation(
    bookmark_id: int, 
    db: Session = Depends(get_session)
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
def get_rss_feed(db: Session = Depends(get_session)):
    """Generates and serves the dynamic Podcast RSS XML feed."""
    statement = select(Bookmark).where(Bookmark.status == "completed").order_by(Bookmark.added_at.desc())
    completed_bookmarks = db.exec(statement).all()
    
    rss_xml = generate_podcast_rss(completed_bookmarks)
    return Response(content=rss_xml, media_type="application/xml")


# ----------------- Settings API -----------------

@app.get("/api/settings")
def get_all_settings(db: Session = Depends(get_session)):
    """Returns all user-configurable settings grouped by section."""
    settings = db.exec(select(Setting)).all()
    result: Dict[str, Dict[str, str]] = {}
    for s in settings:
        if s.section not in result:
            result[s.section] = {}
        result[s.section][s.key] = s.value
    return result


@app.post("/api/settings")
def update_setting(
    key: str = Form(...),
    value: str = Form(...),
    section: str = Form("general"),
    db: Session = Depends(get_session),
):
    """Create or update a single setting."""
    setting = set_setting(db, key, value, section)
    logger.info(f"Setting updated: [{section}] {key} = {value}")
    return {"status": "success", "section": setting.section, "key": setting.key, "value": setting.value}


# ----------------- TTS Engine API -----------------

@app.get("/api/tts/engines")
def get_tts_engines():
    """Lists all registered TTS engines and their installation status."""
    return {"engines": list_available_engines()}


@app.get("/api/tts/voices/{engine}")
def get_voices_for_engine(engine: str):
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


@app.post("/api/tts/reference")
async def upload_reference_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
):
    """Upload a reference WAV file for voice cloning (Pocket TTS)."""
    if not file.filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are supported for reference audio.")
    
    try:
        contents = await file.read()
        REFERENCE_WAV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REFERENCE_WAV_PATH, "wb") as f:
            f.write(contents)
        
        # Update the setting to indicate a reference is available
        set_setting(db, "reference_audio", str(REFERENCE_WAV_PATH), section="tts")
        
        logger.info(f"Reference audio uploaded: {REFERENCE_WAV_PATH} ({len(contents)} bytes)")
        return {
            "status": "success",
            "message": "Reference audio uploaded successfully.",
            "path": str(REFERENCE_WAV_PATH),
            "size": len(contents),
        }
    except Exception as e:
        logger.error(f"Failed to upload reference audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mount general static assets (js, css, images) under `/frontend`
app.mount("/frontend", StaticFiles(directory=str(BASE_DIR / "frontend")), name="frontend")
