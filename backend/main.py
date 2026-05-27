import os
import logging
from typing import List
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from backend.config import BASE_DIR, AUDIO_DIR
from backend.database import init_db, get_session, Bookmark
from backend.syncer import sync_raindrops
from backend.rss_generator import generate_podcast_rss

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

# Mount general static assets (js, css, images) under `/frontend`
app.mount("/frontend", StaticFiles(directory=str(BASE_DIR / "frontend")), name="frontend")
