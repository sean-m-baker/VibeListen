import os
import logging
from typing import List
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from backend.config import BASE_DIR, AUDIO_DIR, DEFAULT_VOICE
from backend.database import init_db, get_session, Bookmark
from backend.syncer import sync_raindrops
from backend.parser import extract_article_content
from backend.tts import generate_podcast_audio
from backend.rss_generator import generate_podcast_rss

# Setup server logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VibeListen")

app = FastAPI(title="VibeListen", description="Personal Read-it-Later Podcast Server")

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
        return {"message": "Welcome to VibeListen API! Dashboard index.html is not created yet."}
    return FileResponse(index_path)

# Mount audio storage directory under `/audio` to serve synthesized MP3 enclosures
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# ----------------- Background Worker Tasks -----------------

async def process_bookmark_pipeline(bookmark_id: int, db: Session):
    """
    Background worker that runs the full bookmark processing pipeline:
    1. Parses & cleans HTML text from the URL
    2. Runs Edge TTS to generate the podcast track
    3. Saves final metadata & completes status
    """
    # Fetch bookmark inside worker context
    bookmark = db.get(Bookmark, bookmark_id)
    if not bookmark:
        logger.error(f"Worker Pipeline failed: Bookmark ID {bookmark_id} not found.")
        return

    logger.info(f"Starting pipeline for bookmark {bookmark_id}: '{bookmark.title}'")
    
    # Step 1: Parse content
    try:
        bookmark.status = "parsing"
        db.add(bookmark)
        db.commit()
        
        clean_text = extract_article_content(bookmark.url)
        
        # Save text and update status
        bookmark.clean_text = clean_text
        bookmark.status = "synthesizing"
        db.add(bookmark)
        db.commit()
    except Exception as e:
        logger.exception(f"Parsing failed for bookmark {bookmark_id}")
        bookmark.status = "parsing_failed"
        db.add(bookmark)
        db.commit()
        return

    # Step 2: Speech synthesis
    try:
        filename = f"raindrop_{bookmark.raindrop_id}.mp3"
        output_path = AUDIO_DIR / filename
        
        # Async execution of Edge-TTS synthesizer
        stats = await generate_podcast_audio(
            text=bookmark.clean_text,
            title=bookmark.title,
            author=bookmark.author or "Unknown Author",
            output_path=str(output_path),
            voice=DEFAULT_VOICE
        )
        
        # Update database with success state
        bookmark.audio_filename = filename
        bookmark.audio_filesize = stats["filesize"]
        bookmark.audio_duration = stats["duration"]
        bookmark.status = "completed"
        bookmark.generated_at = datetime.utcnow()
        db.add(bookmark)
        db.commit()
        logger.info(f"Pipeline completed successfully for bookmark {bookmark_id}")
    except Exception as e:
        logger.exception(f"Synthesis failed for bookmark {bookmark_id}")
        bookmark.status = "failed"
        db.add(bookmark)
        db.commit()

# ----------------- API Endpoints -----------------

@app.get("/api/bookmarks", response_model=List[Bookmark])
def list_bookmarks(db: Session = Depends(get_session)):
    """Lists all bookmarks in the SQLite database, newest first."""
    statement = select(Bookmark).order_by(Bookmark.added_at.desc())
    return db.exec(statement).all()

@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_session)):
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
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_session)
):
    """Adds article cleaning and audio synthesis for a bookmark into the background thread pool queue."""
    bookmark = db.get(Bookmark, bookmark_id)
    if not bookmark:
        raise HTTPException(status_code=404, detail="Bookmark not found")
        
    if bookmark.status in ["parsing", "synthesizing"]:
        return {"status": "already_running", "message": "Synthesis pipeline is already executing."}
        
    # Queue task to FastAPI worker pool
    background_tasks.add_task(process_bookmark_pipeline, bookmark_id, db)
    
    # Mark in DB that task is queued
    bookmark.status = "queued"
    db.add(bookmark)
    db.commit()
    
    return {"status": "queued", "message": "Bookmark added to compilation background queue."}

@app.get("/rss.xml")
def get_rss_feed(db: Session = Depends(get_session)):
    """Generates and serves the dynamic Podcast RSS XML feed."""
    statement = select(Bookmark).where(Bookmark.status == "completed").order_by(Bookmark.added_at.desc())
    completed_bookmarks = db.exec(statement).all()
    
    rss_xml = generate_podcast_rss(completed_bookmarks)
    return Response(content=rss_xml, media_type="application/xml")

# Mount general static assets (js, css, images) under `/frontend`
app.mount("/frontend", StaticFiles(directory=str(BASE_DIR / "frontend")), name="frontend")
