n# VibeListen — Security & Performance Review

> Generated 2026-06-30
> 

## Critical Security Issues

### 1. SSRF — No URL Validation in `backend/parser.py:23`

```python
response = requests.get(url, headers=headers, timeout=15)
```

`extract_article_content()` fetches user-supplied URLs with no allowlist or
blocklist. An attacker who injects a bookmark URL (or compromises a linked
service) can hit internal network services, cloud metadata endpoints
(`169.254.169.254`), or localhost services. `requests` follows redirects by
default, widening the attack surface.

**Fix:** Validate URLs against a blocklist of private/reserved IP ranges before
making the request.

---

### 2. No Authentication on Any API Endpoint — `backend/main.py:48-203`

Every endpoint is completely unauthenticated:

| Method | Path | What it exposes |
| --- | --- | --- |
| `GET` | `/api/bookmarks` | All bookmarks |
| `POST` | `/api/sync` | Triggers external API calls (rate-limit consumption) |
| `POST` | `/api/generate/{id}` | Queues unlimited processing (disk fill) |
| `GET` | `/rss.xml` | Podcast feed |
| `GET` | `/api/settings` | **All stored secrets** (tokens, passwords, OAuth keys) |
| `POST` | `/api/settings` | **Overwrites any setting** |
| `POST` | `/api/tts/reference` | Uploads arbitrary files |

**Fix:** Add authentication (API key header, session-based, or shared secret).

---

### 3. Credentials Stored in Plaintext in SQLite — `backend/database.py:36-47`

The `Setting.value` field is a plain `str` column with no encryption at rest.
Stored secrets include: `raindrop_token`, `instapaper_consumer_key/secret`,
`instapaper_username/password`, `instapaper_oauth_token/secret`.

Anyone with filesystem access to the DB file or a network path to
`GET /api/settings` reads all credentials.

**Fix:** Encrypt secret values at rest (e.g. `cryptography.fernet`). Redact
secret values in `GET /api/settings`.

---

### 4. CORS Misconfiguration — `backend/main.py:25-31`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`Access-Control-Allow-Origin: *` combined with
`Access-Control-Allow-Credentials: true` is **invalid per the CORS spec** and
rejected by browsers. If the app ever relies on cookies for auth (future), this
would be a vulnerability.

**Fix:** Remove `allow_credentials=True` or use explicit `allow_origins`.

---

### 5. No File Size Limit on Reference Audio Upload — `backend/main.py:176`

```python
contents = await file.read()
```

The entire uploaded file is read into memory with no size cap. An attacker can
upload multi-gigabyte files to cause OOM or fill disk.

**Fix:** Check `Content-Length` or set `max_size` on `File()` before reading.

---

### 5b. SSRF / Path Traversal via Route Parameter in `/rss-audio/` Route — `backend/main.py:50`

```python
@app.get("/rss-audio/{filename:path}")
async def serve_rss_audio(filename: str, db: Session = Depends(get_session)):
    ...
    stem = filename[:-4]
    wav_filename = stem + ".wav"
    wav_path = AUDIO_DIR / wav_filename
    ...
    mp3_path = AUDIO_CACHE_DIR / filename
```

The route parameter uses the `:path` type, allowing slashes and traversal sequences. An attacker can request paths like `/rss-audio/../../etc/passwd.mp3` to check the existence of `.wav` files outside the designated audio folder. More critically, the transcoding logic saves the output directly to `AUDIO_CACHE_DIR / filename`. This allows an attacker to write transcoded MP3 files to arbitrary system directories where the server process has write access.

**Fix:** Resolve and verify that the target paths lie strictly within the intended directories (`AUDIO_DIR` and `AUDIO_CACHE_DIR`) using `.resolve()` and checking path containment, or sanitize the filename to remove all directory traversal elements.

---

## High Severity Security Issues

### 6. Path Traversal Risk in Audio Filenames — `backend/worker.py:131-132`

```python
stem = f"raindrop_{bookmark.raindrop_id}" if bookmark.raindrop_id else f"instapaper_{bookmark.instapaper_id}"
output_path = AUDIO_DIR / f"{stem}.mp3"
```

Bookmark IDs come from external APIs and are used unsanitized in filesystem
paths and RSS URLs. A crafted ID (`../../etc/`) could write files outside the
audio directory or craft arbitrary RSS URLs.

**Fix:** Sanitize IDs used in filenames (cast to int, strip non-alphanumeric).

---

### 7. Exception Details Leaked to Clients — `backend/main.py:62, 203`

```python
raise HTTPException(status_code=500, detail=str(e))
```

Raw exception messages can leak internal file paths, network topology, and
third-party error details.

**Fix:** Log the full exception server-side; return a generic message.

---

### 8. Upload Validated by Extension Only — `backend/main.py:169`

```python
if not file.filename.endswith(".wav"):
```

The check only verifies the filename suffix, not the actual file content. The
subsequent `wave.open()` call validates the WAV format but `wave` has had CVEs
(e.g. CVE-2019-20907 — infinite loop).

**Fix:** Validate RIFF magic bytes (`b"RIFF"` at offset 0) and add a timeout.

---

### 9. No Rate Limiting on Any Endpoint

No `slowapi` or similar middleware. Enables: repeated sync calls (API quota
exhaustion), repeated generate calls (disk fill), repeated uploads (disk fill).

**Fix:** Add rate-limiting middleware.

---

### 10. No CSRF Protection on Any POST Endpoint — `backend/main.py:54-203`

All state-changing POST endpoints lack CSRF tokens. While CORS offers some
defense, the CORS misconfiguration (issue #4) makes this worse.

**Fix:** Require a custom header (`X-Requested-By: VibeListen`) or CSRF tokens.

---

### 10b. Arbitrary File Deletion / Path Traversal in Bookmark Deletion — `backend/main.py:95-120`

```python
if bookmark.audio_filename:
    audio_path = AUDIO_DIR / bookmark.audio_filename
    if audio_path.exists():
        audio_path.unlink()
```

If an attacker compromises the external sync endpoints or directly injects a bookmark with an `audio_filename` containing path traversal sequences (e.g. `../../etc/cron.d/malicious`), deleting the bookmark will result in deleting that arbitrary file on disk.

**Fix:** Sanitize `audio_filename` on deletion (or when saving to the database) to ensure it only contains alphanumeric characters, underscores, and dots, and does not perform traversal.

---

## Moderate Security Issues

### 11. Partial Token Logged — `backend/syncer.py:34-35`

```python
masked_token = token[:6] + "..." + token[-4:]
logger.info(...)
```

First 6 + last 4 characters leaked to logs reduces effective keyspace.

**Fix:** Log only whether the token is configured, never any part of its value.

---

### 12. All Instapaper Bookmarks Share RSS GUID — `backend/rss_generator.py:76`

```python
xml.append(f'      <guid isPermaLink="false">VibeListen_{item.raindrop_id}</guid>')
```

For Instapaper bookmarks (`raindrop_id` is `None`), every episode gets GUID
`VibeListen_None`. Podcast apps use GUIDs to identify episodes — all Instapaper
bookmarks collapse to one entry or cause corrupted subscriptions.

**Fix:** Use `instapaper_id` when `raindrop_id` is `None`.

---

### 13. Signal Handlers Registered at Module Import Time — `backend/worker.py:26-27`

```python
signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)
```

Registered when the module is imported, not when `run_worker()` is called.
Importing the module in tests or from the FastAPI process registers handlers
in the parent process.

**Fix:** Move signal registration inside `run_worker()`.

---

### 14. Settings API Returns All Secrets Unredacted — `backend/main.py:95-104`

`GET /api/settings` returns every setting in plaintext with no redaction.
Combined with no authentication (issue #2), this is complete credential
disclosure.

**Fix:** Redact secret values in the response.

---

### 15. Stored XSS via Unescaped Bookmark Domain in Dashboard — `frontend/app.js:266`

```javascript
card.innerHTML = `
    ...
    <span class="card-domain">${b.domain}</span>
    ...
`;
```

While bookmark titles and authors are escaped using `escapeHTML()`, the domain field is directly interpolated into `innerHTML`. If a bookmark is imported with a malicious domain containing HTML elements (e.g., from an attacker-controlled Raindrop account), it will execute arbitrary JavaScript in the context of the user's dashboard session.

**Fix:** Wrap the domain rendering in `escapeHTML(b.domain)` before injecting it into the DOM.

---

## Performance Issues

### 16. Blocking I/O in Async Functions (Multiple Locations)

| Location | File | Line(s) |
| --- | --- | --- |
| Sync `requests.get()` for article parsing | `worker.py` | 109 |
| Sync SQLite queries in async handlers | `main.py` | Various |
| Sync file writes in all TTS engines | `edge_engine.py`, `piper_engine.py`, `pocket_engine.py` | Each |
| Sync `wave.open()` / `sphn.write_wav()` | `piper_engine.py`, `pocket_engine.py` | Each |

All synchronous operations block the asyncio event loop. During long requests,
the worker cannot respond to shutdown signals or process other bookmarks.

**Fix:** Run blocking ops in a thread pool executor or use true async
libraries (`httpx.AsyncClient`, `aiofiles`, `aiosqlite`).

---

### 17. SQLite Without WAL Mode — `backend/database.py:11-12`

No `PRAGMA journal_mode=WAL` or `PRAGMA busy_timeout`. With
`check_same_thread=False` and concurrent readers/writers (FastAPI + background
worker), the default delete-mode journal causes severe write contention.

**Fix:**

```python
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA busy_timeout=5000"))
```

---

### 18. No Index on `status` Column — `backend/database.py:31`

`status` is used in `WHERE` clauses in:

- Worker polling every 2 seconds (`WHERE status == "queued"`)
- RSS feed generation (`WHERE status == "completed"`)
- Bookmark listing

Without an index, all of these perform full table scans.

**Fix:**

```python
status: str = Field(default="pending", index=True)
```

---

### 19-20. N+1 Queries During Sync — `backend/syncer.py:77-78, 240-241`

```python
statement = select(Bookmark).where(Bookmark.raindrop_id == raindrop_id)
existing = session.exec(statement).first()
```

A separate SELECT for each of 50 bookmarks during both Raindrop and Instapaper
sync. 50+ queries per sync operation.

**Fix:** Fetch all existing IDs in a single query before the loop.

---

### 21. Busy Polling When Idle — `backend/worker.py:180-190`

```python
while not _shutdown_requested:
    with Session(engine) as session:
        bookmark = claim_next_bookmark(session)
        if not bookmark:
            await asyncio.sleep(poll_interval)
```

Creates a DB session and SELECT every 2 seconds when no bookmarks are queued.
~43,200 unnecessary queries per day.

**Fix:** Increase poll interval when idle or use an event-driven wakeup.

---

### 22. Three Separate Commits — `backend/worker.py:37-49`

`reset_stalled_bookmarks()` commits separately for each of three status values
("processing", "parsing", "synthesizing") when a single commit suffices.

**Fix:** Single `session.commit()` after the loop.

---

### 23. Duration Estimated via Magic Number — `backend/tts_engines/edge_engine.py:67`

```python
estimated_duration = filesize / 3000.0
```

Assumes ~24 kbps constant bitrate for Edge TTS MP3 output. Actual bitrate
varies by voice, speech rate, and content — the estimate can be 2-5x off.

**Fix:** Use `ffprobe`, `mutagen`, or `pydub` for actual duration.

---

### 24. New Communicate Object Per Chunk — `backend/tts_engines/edge_engine.py:61`

```python
communicate = edge_tts.Communicate(chunk_text, voice)
```

A new HTTP/SSE connection to Microsoft's Edge TTS API is created for each
text chunk. If the library supports single-connection streaming, chunking is
wasteful.

**Fix:** Investigate if `edge_tts.Communicate` handles long text natively.

---

### 25. Fragile Extension Logic — `backend/worker.py:131-147`

Worker passes `output_path` with `.mp3` extension to all engines, but
Piper/Pocket internally swap to `.wav`. Worker checks `.mp3` first, falls
back to `.wav`. A new engine with a different extension would break silently.

**Fix:** Have engines return their actual output path as part of the return
dict.

---

### 26. Full DOM Re-render Every 3 Seconds — `frontend/app.js:326-328`

```jsx
pollingInterval = setInterval(() => { fetchBookmarks(true); }, 3000);
```

`fetchBookmarks` destroys and recreates all bookmark DOM elements on every
poll. For many bookmarks, this causes layout thrashing and jank.

**Fix:** Use targeted DOM updates or increase the poll interval.

---

### 27. Piper `_get_voice` Race Condition — `backend/tts_engines/piper_engine.py:77-109`

```python
if voice_name in self._voice_cache:
    return self._voice_cache[voice_name]
voice = PiperVoice.load(str(model_path))
self._voice_cache[voice_name] = voice
```

No lock around the cache check + model load. Multiple concurrent calls for an
uncached voice call `PiperVoice.load()` (ONNX model loading, not thread-safe)
multiple times.

**Fix:** Use a `threading.Lock` around the critical section.

---

### 28. Pocket `_VOICES_CACHE` Global Without Lock — `backend/tts_engines/pocket_engine.py:53-71`

Module-level global `_VOICES_CACHE` is read and written without
synchronization. Two threads expiring the TTL simultaneously both re-fetch
from HuggingFace and race on the write.

**Fix:** Use a `threading.Lock` around the cache refresh section.

---

### 29. Combined Connect/Read Timeout — `backend/parser.py:23`

```python
response = requests.get(url, headers=headers, timeout=15)
```

A single combined timeout (connect + read). After connection is established,
a slow server sending 1 byte/second can keep the socket open indefinitely.

**Fix:** Use a tuple: `timeout=(10, 30)` (10s connect, 30s read).

---

### 30. No Retry Logic — `backend/syncer.py`, `backend/parser.py`

Transient network failures cause immediate failure of the entire sync or
generation operation. No retry with exponential backoff anywhere.

**Fix:** Use `tenacity`/`backoff` or `HTTPAdapter(max_retries=...)`.

---

### 30b. Chatty and Sequential Settings Saves — `frontend/app.js:677-774`

Saving speech settings triggers 3 sequential POST requests, and saving sync settings triggers up to 8 sequential POST requests. Each request executes a separate HTTP call and database transaction with its own SQLite commit. This chatty behavior is highly inefficient, increases network overhead, and easily triggers SQLite "database is locked" errors due to rapid sequential write-lock acquisitions.

**Fix:** Redesign the settings API to accept a single JSON payload representing multiple settings and process them in a single database transaction.

---

### 30c. PyTorch CPU Core Over-utilization and Event Loop Starvation — `backend/tts_engines/pocket_engine.py`

When running without CUDA, PyTorch defaults to using all available CPU threads (cores) for model inference during Pocket TTS generation (`self._tts.simple_generate(...)`). This causes the worker process to consume 100% of all CPU cores, starving the launcher process and the FastAPI web server, leading to severe dashboard timeouts and API unresponsiveness during synthesis.

**Fix:** Limit the number of threads PyTorch is permitted to spawn by calling `torch.set_num_threads(1)` or a similar low number on engine initialization.

---

### 31. Synchronous HuggingFace Network Requests in PocketEngine — `backend/tts_engines/pocket_engine.py:61, 96`

During the synthesis pipeline, `PocketEngine` calls `list_repo_files` and `hf_hub_download` synchronously to fetch available voices and download models from HuggingFace. These blocking network calls run directly in the async worker's thread, freezing the worker completely and preventing it from responding to shutdown signals or status updates until the files are downloaded.

**Fix:** Offload these blocking network calls to a thread pool executor using `asyncio.to_thread`.

---

## Code Quality Nits

| # | Issue | File | Line |
| --- | --- | --- | --- |
| 32 | Raw `sqlite3` migration bypasses SQLModel type system | `database.py` | 76-118 |
| 33 | Duplicate `asynccontextmanager` import on consecutive lines | `main.py` | 4-5 |
| 34 | Python 3.10+ syntax (`list[str] \| None`) without documented minimum | `pocket_engine.py` | 21 |
| 35 | Unused XML import and manual string-based XML building | `rss_generator.py` | 3 |

### 35. Unused XML Import and Manual String-based XML Building — `backend/rss_generator.py:3`

The module imports `xml.etree.ElementTree as ET` but constructs the podcast feed manually via string concatenation. This manual string generation is fragile and prone to escaping issues. For example, standard escaping using `xml.sax.saxutils.escape` does not encode quotes by default, which can result in malformed XML feed attributes if titles or author names contain quotes.

**Fix:** Construct the RSS XML tree using the standard library (`xml.etree.ElementTree`) or another proper XML builder to ensure correct escaping and formatting of all tags and attributes.