# Implementation Plan: Settings Pages + RSS Timeout Fixes

## Overview

Two independent features with no shared dependencies:

| Feature | Backend Changes | Frontend Changes | New Files/Dirs |
|---------|----------------|-----------------|----------------|
| Separate Settings Pages | None | `index.html`, `app.js`, `styles.css` | None |
| RSS Timeout Fixes | `main.py`, `rss_generator.py`, `database.py`, `config.py` | `index.html`, `app.js` | `data/audio_cache/` |

---

## Feature 1: Separate Settings Pages (SPA Sections + Hash Routing)

### Navigation Change

Current header:
```
[VibeListen] [Sync Library] [Podcast RSS] [⚙️]
```

New header:
```
[VibeListen] [Sync Library] [Podcast RSS] [Settings ▼]
                                          ├─ Speech Settings
                                          └─ Sync Settings
```

The gear icon is replaced with a "Settings" button that opens a dropdown. The dropdown uses the same glassmorphism styling as the rest of the UI.

### SPA Section Structure

Three navigable views, controlled by URL hash:

| Hash | View | Content |
|------|------|---------|
| `#dashboard` (default) | Bookmarks grid (current main view) | Stats cards, search/filter, bookmark grid |
| `#speech` | Speech settings | TTS Engine, Voice, Reference Audio, Audio Bitrate |
| `#sync` | Sync settings | Sync Service, Raindrop Token, Instapaper credentials, Max RSS Items |

Each settings section:
- Replaces the `<main>` element (the bookmarks grid area) — not a modal
- Has a "← Dashboard" link at the top-left
- Has its own Save button at the bottom
- Loads fresh settings data from `/api/settings` when navigated to
- Uses existing `.settings-group`, `.settings-select`, `.settings-input` CSS classes

### Unsaved Changes Detection

- Track a `dirty` flag per-settings view
- Set `dirty = true` on any `change` or `input` event in the settings form
- When navigating away via hash change, if dirty is true → show a native `confirm()` dialog: "You have unsaved changes. Leave anyway?"
- On Save → reset dirty flag, show success toast

### Hash Router (~20 lines in `app.js`)

```javascript
function handleNavigation() {
    const hash = window.location.hash.slice(1) || "dashboard";
    document.querySelectorAll(".view-section").forEach(s => s.classList.remove("active"));
    const target = document.getElementById(`view-${hash}`);
    if (target) target.classList.add("active");

    if (hash === "speech") loadSpeechSettings();
    if (hash === "sync") loadSyncSettings();
    if (hash === "dashboard") fetchBookmarks();
}

window.addEventListener("hashchange", () => {
    if (confirmUnsavedChanges()) handleNavigation();
});
```

### HTML Changes

- Remove entire settings modal (`#modal-settings`) from `index.html`
- Add three view sections inside `.app-container`:
  - `#view-dashboard` (existing main content, wrapped in a section)
  - `#view-speech` (new — speech settings form)
  - `#view-sync` (new — sync settings form)
- Add dropdown menu HTML near the `.actions` div
- Add `#btn-settings-dropdown` and dropdown menu items

### CSS Changes

- Add `.dropdown` styles (container, trigger, menu, items) matching glassmorphism theme
- Add `.view-section` styles (display:none by default, `display:block` when `.active`)
- Add `.back-link` style for the "← Dashboard" link
- Settings styles already exist in `styles.css:798-953` — reusable

---

## Feature 2: RSS Timeout Fixes (Transcoding + Limits + Caching)

### Root Cause

User uses **Piper TTS** which outputs **WAV files**. Piper produces 16-bit mono WAV at 22050 Hz. A 10-minute article ≈ **13 MB WAV**. On mobile networks (especially via tunneling), podcast apps hit 15-30 second download timeouts and fail to play episodes. The RSS XML itself loads fine.

### 2a: Configurable RSS Item Limit

**Backend:**
- `backend/rss_generator.py` — Add `limit` parameter to `generate_podcast_rss()`, cap items returned
- `backend/main.py` — Read `max_rss_items` setting in `/rss.xml` handler, pass to generator
- New setting: section=`general`, key=`max_rss_items`, default=`"100"`

**Frontend:**
- Add "Max RSS Items" number input in Sync Settings section
- Saves to `/api/settings` with section=`general`, key=`max_rss_items`

### 2b: WAV→MP3 On-the-Fly Transcoding

**New Config:**
- `backend/config.py` — Add `AUDIO_CACHE_DIR`

**New Setting:**
- section=`tts`, key=`audio_bitrate`, default=`"64"`

**New Endpoint in `backend/main.py`:**

```python
@app.get("/rss-audio/{filename:path}")
async def serve_rss_audio(filename: str, db: Session = Depends(get_session)):
    """Serve WAV files transcoded to MP3 for mobile podcast app compatibility."""
    if not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only MP3 output is supported")

    stem = filename[:-4]
    wav_filename = stem + ".wav"
    wav_path = AUDIO_DIR / wav_filename

    if not wav_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    bitrate = get_setting(db, "audio_bitrate", "64", section="tts")
    mp3_path = AUDIO_CACHE_DIR / filename

    if not mp3_path.exists():
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame",
            "-b:a", f"{bitrate}k",
            "-ar", "24000",       # Preserve sample rate
            "-ac", "1",           # Mono
            str(mp3_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode != 0:
            raise HTTPException(status_code=500, detail="Audio transcoding failed")

    return FileResponse(mp3_path, media_type="audio/mpeg", filename=filename)
```

**RSS Generator Update** (`backend/rss_generator.py`):
- Accept `bitrate` parameter (string, e.g. `"64"`)
- For WAV files, point enclosure URL to `/rss-audio/{stem}.mp3`
- Estimate compressed filesize from bitrate × duration
- Hardcoded list updated: MP3 files keep pointing to `/audio/`

### 2c: ETag/Last-Modified Caching

In `backend/main.py` `/rss.xml` handler:
- Compute ETag as hash of the most recent completed bookmark's `generated_at` timestamp
- Check `If-None-Match` request header → return `304 Not Modified` if matches
- Set `ETag` and `Cache-Control: no-cache` response headers

### 2d: DB Index

In `backend/database.py` `migrate_database()`:
- Add composite index: `CREATE INDEX IF NOT EXISTS ix_bookmark_status_added_at ON bookmark (status, added_at DESC)`
- Uses existing `sqlite3` connection already used for migrations

### 2e: Accept-Ranges Verification

Starlette's `FileResponse` already handles `Accept-Ranges` and `Content-Range`. Verify with a test that a ranged request returns `206 Partial Content`. No code change — just test coverage.

---

## Frontend Settings: New Fields to Add

### Speech Settings section
| Field | Type | Default | Hint |
|-------|------|---------|------|
| TTS Engine | select (existing) | — | — |
| Voice | select (existing) | — | — |
| Reference Voice | file upload (existing) | — | — |
| Audio Bitrate | number input (NEW) | 64 | MP3 bitrate for mobile RSS downloads (kbps) |

### Sync Settings section
| Field | Type | Default | Hint |
|-------|------|---------|------|
| Sync Service | select (existing) | — | — |
| Raindrop Token | password (existing) | — | — |
| Instapaper fields | text/password (existing) | — | — |
| Max RSS Items | number input (NEW) | 100 | Maximum episodes in the RSS feed |

---

## Testing

| Test | Type | File |
|------|------|------|
| Speech settings UI loads and saves | Frontend | Manual + existing `test_settings.py` |
| Sync settings UI loads and saves | Frontend | Manual + existing `test_settings.py` |
| Hash routing navigation | Frontend | Manual |
| Unsaved changes prompt | Frontend | Manual |
| `/rss.xml` returns ≤ N items | Backend | `tests/test_rss.py` (new) |
| `/rss.xml` returns 304 on matching ETag | Backend | `tests/test_rss.py` (new) |
| `/rss-audio/{file}.mp3` transcodes WAV | Backend | `tests/test_rss.py` (new) |
| `/rss-audio/{file}.mp3` returns 206 with Range | Backend | `tests/test_rss.py` (new) |
| Audio bitrate setting changes output | Backend | `tests/test_rss.py` (new) |
| Max RSS Items setting affects feed | Backend | `tests/test_rss.py` (new) |

---

## Execution Order

Recommended order since features are independent:

1. **Backend: RSS fixes first** — new `/rss-audio` endpoint, ETag caching, DB index, RSS item limit
2. **Backend: New settings** — `audio_bitrate`, `max_rss_items` are just DB writes, no schema changes
3. **Frontend: Settings pages** — rewrite settings UI with hash routing, sections, dropdown, unsaved-changes prompt
4. **Frontend: New settings fields** — add bitrate and max RSS items to their respective pages
5. **Tests** — add/update tests for all new functionality

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| ffmpeg not installed → transcoding fails | Check availability on startup; log warning; fall back to serving WAV directly; document in setup |
| Hash routing conflicts with existing SPA behavior | `handleNavigation()` called on init and on `hashchange`; only manages view visibility |
| Cache directory (`audio_cache/`) grows unbounded | Document that `rm -rf data/audio_cache` is safe; add "Clear Cache" button post-v1 |
| Unsaved changes prompt is too aggressive | Only fires on `hashchange` away from dirty section; not on browser close |
| Back button with hash routing | Native browser back navigates through hash history correctly by default |
| Large audio files on first transcode | Acceptable ~1s per file on first request; cached for subsequent requests |
| Piper outputs at 22050 Hz but we transcode to 24000 | ffmpeg handles sample rate conversion transparently; quality impact is negligible |
