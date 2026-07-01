# Phase 4 — Security & Performance Remediation Plan

> Based on `security_performance_analysis.md` (generated 2026-06-30)
>
> Branch: `v0.6`

This plan is organized using an **Agile Framework**. The scope is broken down into **Waves (Epics)**, **Features (Issues)**, and actionable **Tasks** with specific **Acceptance Criteria** and **Testing** requirements.

Issues are numbered according to the original analysis document.

---

## Wave 0 — Foundation & Prerequisites

Lays the groundwork required by subsequent security and performance fixes.

---

### Feature 0.1: Add Required Dependency Packages

**As a** developer,
**I want** the required library dependencies declared in `requirements.txt`,
**So that** code changes in later waves have their packages available.

#### Tasks
- [ ] **Task 0.1.1**: Add to `requirements.txt`:
  - `cryptography>=41.0.0` (Fernet encryption for credential storage — Wave 1, issue #3)
  - `slowapi>=0.1.9` (rate limiting middleware — Wave 2, issue #9)
  - `tenacity>=8.2.0` (retry logic — Wave 3, issue #30)
  - `mutagen>=1.47.0` (accurate audio duration — Wave 3, issue #23)
  - `httpx>=0.25.0` (async HTTP client — Wave 3, issue #16)
  - `aiofiles>=23.2.0` (async file I/O — Wave 3, issue #16)
- [ ] **Task 0.1.2**: Run `pip install -r requirements.txt` to verify all new packages resolve and install cleanly.

#### Testing
- Verify `pip install -r requirements.txt` completes without errors.
- Run `python -c "from cryptography.fernet import Fernet; print('ok')"` (and similar for each new package).

---

### Feature 0.2: Add SECRET_KEY Environment Configuration

**As a** developer,
**I want** a `SECRET_KEY` configuration value available to the application,
**So that** Fernet encryption (issue #3) and API key auth (issue #2) have a cryptographically sound key source.

#### Tasks
- [ ] **Task 0.2.1**: Add `SECRET_KEY=` to `.env.example` with a comment: `# Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] **Task 0.2.2**: Add to `backend/config.py`:
  ```python
  SECRET_KEY: str = os.getenv("SECRET_KEY", "")
  if not SECRET_KEY:
      raise RuntimeError("SECRET_KEY environment variable is required. Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
  ```
- [ ] **Task 0.2.3**: Generate a fresh `SECRET_KEY` and add to local `.env` for the development environment (documented, not committed).

#### Testing
- Verify startup fails with a clear error when `SECRET_KEY` is absent.
- Verify startup succeeds when `SECRET_KEY` is set.

---

### Feature 0.3: Create Shared Security Utilities Module

**As a** developer,
**I want** a single `backend/auth.py` module containing shared authentication, encryption, and security helpers,
**So that** all waves can use consistent implementations without code duplication.

#### Tasks
- [ ] **Task 0.3.1**: Create `backend/auth.py` with:
  - `get_api_key_dependency()` — FastAPI dependency that checks `X-API-Key` header against `SECRET_KEY` (for issue #2).
  - `encrypt_secret(plaintext: str) -> str` / `decrypt_secret(ciphertext: str) -> str` — Fernet wrapper functions (for issue #3).
  - `REDACTED_SECRET_KEYS` — set of key name substrings (`"token"`, `"secret"`, `"password"`, `"key"`) for redaction logic (for issues #3, #14).
  - `is_internal_ip(host: str) -> bool` — resolves hostname and checks against private/reserved ranges (for issue #1).
  - `sanitize_filename(name: str) -> str` — strips path separators and traversal sequences (for issues #5b, #6, #10b).
  - `get_csrf_dependency()` — FastAPI dependency checking `X-Requested-By: VibeListen` header (for issue #10).
  - `secret_redactor(value: str) -> str` — returns `"***REDACTED***"` for any value whose key is in `REDACTED_SECRET_KEYS` (for issue #14).
- [ ] **Task 0.3.2**: Write unit tests for each utility function in `tests/test_auth.py`.

#### Testing
- `pytest tests/test_auth.py -v` — cover encrypt/decrypt round-trip, invalid key, internal IP detection, filename sanitization, redaction behaviour.

---

## Wave 1 — Critical Security (P0)

Active exploitation risk — these must be fixed before the server is deployed or exposed to any network.

---

### Feature 1.1: SSRF Protection in Article Parser (Issue #1)

**As a** server operator,
**I want** the article parser to block requests to internal/private IP ranges,
**So that** an attacker cannot use the bookmark URL field to scan or attack internal network services.

#### Tasks
- [ ] **Task 1.1.1**: In `backend/parser.py`, add URL validation before `requests.get()`:
  ```python
  from urllib.parse import urlparse
  import socket
  
  def _validate_url(url: str) -> None:
      parsed = urlparse(url)
      if not parsed.hostname:
          raise ValueError("URL has no hostname")
      if parsed.scheme not in ("http", "https"):
          raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
      try:
          host = parsed.hostname
          addrs = socket.getaddrinfo(host, None)
          for family, _, _, _, sockaddr in addrs:
              ip = sockaddr[0]
              if is_internal_ip(ip):
                  raise ValueError(f"Blocked request to internal IP: {ip}")
      except socket.gaierror:
          raise ValueError(f"Could not resolve hostname: {host}")
  ```
- [ ] **Task 1.1.2**: Import and call `_validate_url(url)` from `extract_article_content()` before the `requests.get()` call.
- [ ] **Task 1.1.3**: Move private-range checking logic into `backend/auth.py:is_internal_ip()` (from Feature 0.3) and use it here.
- [ ] **Task 1.1.4**: Use `functools.lru_cache` on `is_internal_ip` to avoid repeated DNS resolution for the same hostname in a batch.

#### Testing
- `tests/test_parser.py`: Add test cases for:
  - Valid external URL resolves OK.
  - URL pointing to `127.0.0.1`, `10.x.x.x`, `172.16.x.x`, `192.168.x.x`, `169.254.x.x` raises `ValueError`.
  - URL with no scheme or non-HTTP scheme raises `ValueError`.
  - `socket.getaddrinfo` failure is handled gracefully.
- Mock `requests.get` and `socket.getaddrinfo` to avoid actual network calls.

---

### Feature 1.2: API Authentication (Issue #2)

**As a** server operator,
**I want** all API endpoints (except public static files and RSS feed) protected by an API key,
**So that** only authorized clients can read/write data, trigger syncs, or view settings.

#### Tasks
- [ ] **Task 1.2.1**: In `backend/auth.py`, implement `require_api_key` FastAPI dependency:
  ```python
  async def require_api_key(request: Request):
      key = request.headers.get("X-API-Key", "")
      if not key or key != config.SECRET_KEY:
          raise HTTPException(status_code=401, detail="Invalid or missing API key")
  ```
- [ ] **Task 1.2.2**: Apply `require_api_key` to protected endpoints in `backend/main.py`:
  - `GET /api/bookmarks`
  - `POST /api/sync`
  - `POST /api/generate/{bookmark_id}`
  - `DELETE /api/bookmarks/{bookmark_id}`
  - `GET /api/settings`
  - `POST /api/settings`
  - `GET /api/tts/engines`
  - `GET /api/tts/voices/{engine}`
  - `POST /api/tts/reference`
- [ ] **Task 1.2.3**: **Do not** apply auth to:
  - `GET /` (dashboard static page)
  - `GET /rss.xml` (public podcast feed)
  - `GET /audio/{path}` (audio files referenced in RSS)
  - `GET /rss-audio/{path}` (transcoded audio)
  - `GET /frontend/{path}` (static JS/CSS)
- [ ] **Task 1.2.4**: Update `frontend/app.js` to send `X-API-Key` header on all API fetch calls. Read the API key from a meta tag or a new config endpoint (or embed via build-time variable).
- [ ] **Task 1.2.5**: Add `X-API-Key` to CORS `expose_headers` if needed for frontend access.

#### Testing
- `tests/test_main.py`: Add parameterized tests for each endpoint:
  - Without `X-API-Key` header → 401.
  - With wrong `X-API-Key` → 401.
  - With correct `X-API-Key` → normal response (200/404/etc).
  - Public endpoints return normal response without any key.
- Update frontend test/mock to verify header is sent.

---

### Feature 1.3: Credential Encryption at Rest (Issue #3)

**As a** server operator,
**I want** all secret settings values (tokens, passwords, keys) encrypted in the SQLite database,
**So that** a filesystem compromise or database leak does not expose plaintext credentials.

#### Tasks
- [ ] **Task 1.3.1**: In `backend/auth.py`, implement `encrypt_secret()` and `decrypt_secret()` using `cryptography.fernet.Fernet`:
  ```python
  _fernet = Fernet(config.SECRET_KEY.encode() if isinstance(config.SECRET_KEY, str) else config.SECRET_KEY)
  
  def encrypt_secret(plaintext: str) -> str:
      return _fernet.encrypt(plaintext.encode()).decode()
  
  def decrypt_secret(ciphertext: str) -> str:
      return _fernet.decrypt(ciphertext.encode()).decode()
  ```
- [ ] **Task 1.3.2**: Modify `backend/database.py:set_setting()` — if the key name matches any `REDACTED_SECRET_KEYS` substring, encrypt the value before storing.
- [ ] **Task 1.3.3**: Modify `backend/database.py:get_setting()` — if the key name matches any `REDACTED_SECRET_KEYS` substring, decrypt the value after reading.
- [ ] **Task 1.3.4**: Handle the case where a stored value was not encrypted (e.g. pre-migration data) — attempt decryption, fall back to returning plaintext.
- [ ] **Task 1.3.5**: In `backend/main.py:get_all_settings()`, redact values for keys matching `REDACTED_SECRET_KEYS` before returning to client.

#### Testing
- `tests/test_auth.py`: Test encrypt/decrypt round-trip, decryption of invalid ciphertext raises error.
- `tests/test_database.py`: Write a setting with a secret key, read it back, verify it's stored as Fernet ciphertext (not plaintext). Verify `get_setting` returns the decrypted value. Verify `GET /api/settings` returns `"***REDACTED***"` for secret keys.

---

### Feature 1.4: CORS Misconfiguration Fix (Issue #4)

**As a** developer,
**I want** the CORS configuration to be valid per the CORS specification,
**So that** browsers do not reject responses and future cookie-based auth works correctly.

#### Tasks
- [ ] **Task 1.4.1**: In `backend/main.py`, change CORS middleware to **either**:
  - Option A (recommended): Remove `allow_credentials=True` and keep `allow_origins=["*"]` (if auth is header-based, not cookie-based).
  - Option B: Set explicit `allow_origins` from a config value (e.g. `CORS_ORIGINS` env var) and keep `allow_credentials=True`.
- [ ] **Task 1.4.2**: Add `CORS_ORIGINS` to `.env.example` if using Option B.

#### Testing
- `tests/test_main.py`: Verify `Access-Control-Allow-Origin` header is present on responses. Verify `Access-Control-Allow-Credentials` is not `true` (Option A) or matches the explicit origin (Option B).

---

### Feature 1.5: File Size Limit on Audio Upload (Issue #5)

**As a** server operator,
**I want** the reference audio upload endpoint to enforce a maximum file size,
**So that** an attacker cannot cause OOM or disk exhaustion by uploading multi-gigabyte files.

#### Tasks
- [ ] **Task 1.5.1**: In `backend/main.py:upload_reference_audio()`, add size check before reading file body:
  ```python
  MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
  if request.headers.get("content-length"):
      content_length = int(request.headers["content-length"])
      if content_length > MAX_UPLOAD_SIZE:
          raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB.")
  ```
- [ ] **Task 1.5.2**: Alternatively, use FastAPI's `File(..., max_length=...)` parameter or read in chunks with a running byte counter.

#### Testing
- `tests/test_main.py`: Upload a file exceeding 10 MB → 413. Upload a valid small file → 200 or 400 (format validation).

---

### Feature 1.6: Path Traversal in /rss-audio/ Route (Issue #5b)

**As a** server operator,
**I want** the `/rss-audio/{filename:path}` route to reject path traversal sequences,
**So that** an attacker cannot read or write files outside the designated audio directories.

#### Tasks
- [ ] **Task 1.6.1**: In `backend/main.py:serve_rss_audio()`, add filename sanitization:
  ```python
  from backend.auth import sanitize_filename
  # Reject traversal sequences
  if ".." in filename or "/" in filename or "\\" in filename:
      raise HTTPException(status_code=400, detail="Invalid filename")
  ```
- [ ] **Task 1.6.2**: After constructing `wav_path` and `mp3_path`, use `.resolve()` and verify they are within `AUDIO_DIR` and `AUDIO_CACHE_DIR` respectively:
  ```python
  wav_path = (AUDIO_DIR / wav_filename).resolve()
  if not str(wav_path).startswith(str(AUDIO_DIR.resolve())):
      raise HTTPException(status_code=400, detail="Invalid path")
  ```

#### Testing
- `tests/test_main.py`: Request `/rss-audio/../etc/passwd.mp3` → 400. Request `/rss-audio/valid.mp3` → 404 or 200. Request with encoded traversal → 400.

---

### Feature 1.7: Path Traversal in Bookmark Deletion (Issue #10b)

**As a** server operator,
**I want** the bookmark deletion endpoint to sanitize `audio_filename` before constructing filesystem paths,
**So that** an attacker cannot delete arbitrary files by crafting a malicious `audio_filename`.

#### Tasks
- [ ] **Task 1.7.1**: In `backend/main.py:delete_bookmark()`, sanitize `bookmark.audio_filename` before using it in file operations:
  ```python
  from backend.auth import sanitize_filename
  
  if bookmark.audio_filename:
      safe_filename = sanitize_filename(bookmark.audio_filename)
      if safe_filename != bookmark.audio_filename:
          logger.warning(f"Sanitized audio_filename for bookmark {bookmark_id}: '{bookmark.audio_filename}' -> '{safe_filename}'")
          bookmark.audio_filename = safe_filename
      audio_path = (AUDIO_DIR / safe_filename).resolve()
      if not str(audio_path).startswith(str(AUDIO_DIR.resolve())):
          raise HTTPException(status_code=400, detail="Invalid audio filename")
      if audio_path.exists():
          audio_path.unlink()
  ```
- [ ] **Task 1.7.2**: Also sanitize on the MP3 cache deletion path.

#### Testing
- `tests/test_main.py`: Create a bookmark with `audio_filename = "../../etc/passwd"`, attempt deletion, verify no file outside `AUDIO_DIR` is touched.

---

### Wave 1 Verification
```bash
python -m pytest tests/ -v -k "test_ssrf or test_auth or test_cors or test_upload or test_traversal"
```

---

## Wave 2 — High Security + Critical Performance (P1)

Addresses important security gaps and performance bottlenecks that directly impact reliability and user experience.

### Section A — Security (P1)

---

### Feature 2.1: Audio Filename Path Traversal (Issue #6)

**As a** developer,
**I want** bookmark IDs used in audio filenames to be sanitized,
**So that** crafted IDs from external APIs cannot escape the audio directory.

#### Tasks
- [ ] **Task 2.1.1**: In `backend/worker.py:131-132`, sanitize the stem:
  ```python
  if bookmark.raindrop_id:
      stem = f"raindrop_{abs(bookmark.raindrop_id)}"
  elif bookmark.instapaper_id:
      stem = f"instapaper_{abs(bookmark.instapaper_id)}"
  else:
      stem = f"bookmark_{bookmark.id}"
  ```
- [ ] **Task 2.1.2**: Ensure the stem value is used only for the initial `.mp3` guess, and let the engine's actual output path (Feature 3.10) drive the final filename.

#### Testing
- `tests/test_worker.py`: Verify that IDs containing `../` are sanitized to integers-only filenames.

---

### Feature 2.2: Exception Detail Leaked to Clients (Issue #7)

**As a** server operator,
**I want** exception details logged server-side but never returned to the client,
**So that** internal file paths, network topology, and error internals remain hidden.

#### Tasks
- [ ] **Task 2.2.1**: Audit all `HTTPException(500, detail=str(e))` calls in `backend/main.py`:
  - `trigger_sync()` line 130
  - `upload_reference_audio()` line 290
- [ ] **Task 2.2.2**: Change each to:
  ```python
  logger.error(f"Endpoint failed: {e}")
  raise HTTPException(status_code=500, detail="Internal server error")
  ```
- [ ] **Task 2.2.3**: Add a global exception handler for unhandled exceptions:
  ```python
  @app.exception_handler(Exception)
  async def global_exception_handler(request: Request, exc: Exception):
      logger.exception(f"Unhandled exception on {request.url}: {exc}")
      return JSONResponse(status_code=500, content={"detail": "Internal server error"})
  ```

#### Testing
- `tests/test_main.py`: Trigger a sync failure (mock failure), verify response body is `{"detail": "Internal server error"}` and does not contain internal paths.

---

### Feature 2.3: Upload Content Validation (Issue #8)

**As a** developer,
**I want** the WAV file upload endpoint to validate the actual file content (magic bytes),
**So that** non-WAV files are rejected even if they have a `.wav` extension.

#### Tasks
- [ ] **Task 2.3.1**: In `backend/main.py:upload_reference_audio()`, after reading file content, check RIFF header:
  ```python
  if contents[:4] != b"RIFF":
      raise HTTPException(status_code=400, detail="File is not a valid WAV (missing RIFF header)")
  ```
- [ ] **Task 2.3.2**: Add a timeout guard around `wave.open()` to mitigate CVE-2019-20907 (infinite loop). Since `wave.open()` reads from `io.BytesIO`, this is less risky but add a max-frame sanity check:
  ```python
  if w.getnframes() > 10_000_000:  # ~400 seconds at 24kHz
      raise HTTPException(status_code=400, detail="WAV file has too many frames")
  ```

#### Testing
- `tests/test_main.py`: Upload a non-WAV file with `.wav` extension → 400. Upload a valid WAV → 200. Upload a WAV with malformed header → 400.

---

### Feature 2.4: Rate Limiting (Issue #9)

**As a** server operator,
**I want** rate limiting applied to all API endpoints,
**So that** an attacker cannot abuse sync, generate, or upload endpoints for API quota exhaustion or disk fill.

#### Tasks
- [ ] **Task 2.4.1**: Install and configure `slowapi` in `backend/main.py`:
  ```python
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.util import get_remote_address
  
  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(429, _rate_limit_exceeded_handler)
  ```
- [ ] **Task 2.4.2**: Apply rate limits:
  - `POST /api/sync`: 5 requests per minute
  - `POST /api/generate/{bookmark_id}`: 30 requests per minute
  - `POST /api/tts/reference`: 5 requests per minute
  - `POST /api/settings`: 30 requests per minute
  - `GET /api/*`: 60 requests per minute
- [ ] **Task 2.4.3**: Handle rate-limit headers in `frontend/app.js` with appropriate user-facing messages.

#### Testing
- `tests/test_main.py`: Rapid-fire requests to `POST /api/sync` → 429 after threshold. Verify `Retry-After` header present.

---

### Feature 2.5: CSRF Protection (Issue #10)

**As** a developer,
**I want** all state-changing POST endpoints to require a custom `X-Requested-By` header,
**So that** cross-origin form submissions cannot trigger state changes.

#### Tasks
- [ ] **Task 2.5.1**: In `backend/auth.py`, implement `require_csrf_header` dependency that checks for `X-Requested-By: VibeListen`.
- [ ] **Task 2.5.2**: Apply to all POST endpoints in `backend/main.py` (`/api/sync`, `/api/generate/{bookmark_id}`, `/api/settings`, `/api/tts/reference`).
- [ ] **Task 2.5.3**: Update `frontend/app.js` to send `X-Requested-By: VibeListen` header on all POST requests.

#### Testing
- `tests/test_main.py`: POST without CSRF header → 400. POST with correct header → normal response.
- Update frontend tests to verify header inclusion.

---

### Section B — Performance (P1)

---

### Feature 2.6: SQLite WAL Mode (Issue #17)

**As a** developer,
**I want** SQLite configured with WAL journal mode and a busy timeout,
**So that** concurrent reads from FastAPI and writes from the worker do not cause "database is locked" errors.

#### Tasks
- [ ] **Task 2.6.1**: In `backend/database.py`, add event listener on the engine:
  ```python
  from sqlalchemy import event
  
  @event.listens_for(engine, "connect")
  def set_sqlite_pragma(db_connection, connection_record):
      cursor = db_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA busy_timeout=5000")
      cursor.close()
  ```
- [ ] **Task 2.6.2**: Verify the existing `check_same_thread=False` is still set on `connect_args`.

#### Testing
- `tests/test_database.py`: Connect to a fresh in-memory SQLite, verify `PRAGMA journal_mode` returns `wal`. Verify concurrent read/write does not produce `sqlite3.OperationalError: database is locked`.

---

### Feature 2.7: Add Index on `status` Column (Issue #18)

**As a** developer,
**I want** the `status` column to have a database index,
**So that** queries filtering by status (worker polling, RSS generation, bookmark listing) do not perform full table scans.

#### Tasks
- [ ] **Task 2.7.1**: In `backend/database.py:31`, change the `status` field definition:
  ```python
  status: str = Field(default="pending", index=True)
  ```
- [ ] **Task 2.7.2**: Add a raw SQL migration in `migrate_database()` to create the index for existing databases:
  ```python
  cursor.execute("CREATE INDEX IF NOT EXISTS ix_bookmark_status ON bookmark (status)")
  ```

#### Testing
- `tests/test_database.py`: Create a new database, verify `ix_bookmark_status` index exists via `PRAGMA index_list(bookmark)`.

---

### Feature 2.8: Eliminate N+1 Queries During Sync (Issues #19-20)

**As a** developer,
**I want** the sync logic to fetch all existing bookmark IDs in a single query,
**So that** a 50-bookmark sync does not issue 50+ individual SELECT queries.

#### Tasks
- [ ] **Task 2.8.1**: In `backend/syncer.py:sync_raindrops()`, before the loop:
  ```python
  existing_raindrop_ids = set()
  stmt = select(Bookmark.raindrop_id).where(Bookmark.raindrop_id.isnot(None))
  for row in session.exec(stmt):
      existing_raindrop_ids.add(row[0])
  ```
  Replace the per-item `select(Bookmark).where(Bookmark.raindrop_id == raindrop_id)` with `if raindrop_id in existing_raindrop_ids`.
- [ ] **Task 2.8.2**: Apply the same pattern to `sync_instapaper()` for `instapaper_id`.

#### Testing
- `tests/test_syncer.py`: Mock Raindrop API to return 50 items. Use a spy on `session.exec` to verify only 2 SELECT queries total (one for existing IDs, one is debatable — the N+1 loop should no longer issue individual queries).

---

### Feature 2.9: Bulk Settings API (Issue #30b)

**As a** user,
**I want** saving my settings to use a single HTTP request instead of 3–8 sequential requests,
**So that** settings save quickly and avoid SQLite write-lock contention.

#### Tasks
- [ ] **Task 2.9.1**: Add a new endpoint `POST /api/settings/bulk` in `backend/main.py`:
  ```python
  @app.post("/api/settings/bulk")
  def bulk_update_settings(
      payload: Dict[str, Dict[str, str]],
      db: Session = Depends(get_session),
  ):
      """Update multiple settings in a single request.
      Payload format: {"section": {"key": "value", ...}, ...}
      """
      for section, keys in payload.items():
          for key, value in keys.items():
              set_setting(db, key, value, section)
      return {"status": "success"}
  ```
- [ ] **Task 2.9.2**: Modify `set_setting()` to accept an optional `commit=True` parameter. When called from `bulk_update_settings`, pass `commit=False` and do a single `commit()` after all upserts.
- [ ] **Task 2.9.3**: Update `frontend/app.js:btnSaveSpeechSettings` and `btnSaveSyncSettings` handlers to build a single JSON payload and call `POST /api/settings/bulk`.
- [ ] **Task 2.9.4**: Mark `POST /api/settings` (single-setting) as deprecated or keep for backward compatibility.

#### Testing
- `tests/test_main.py`: Send bulk update with 10 settings, verify all are stored. Verify only 1 DB commit occurred (assert via mock on `session.commit`).
- Frontend: Verify speech settings save sends 1 request, sync settings save sends 1 request.

---

### Feature 2.10: PyTorch CPU Thread Limiting (Issue #30c)

**As a** operator,
**I want** PyTorch to use a limited number of CPU threads during Pocket TTS inference,
**So that** the worker does not consume 100% of all CPU cores and starve the web server.

#### Tasks
- [ ] **Task 2.10.1**: In `backend/tts_engines/pocket_engine.py:PocketEngine.__init__()`, add:
  ```python
  import os
  os.environ["OMP_NUM_THREADS"] = str(max(1, os.cpu_count() // 2 or 1))
  torch.set_num_threads(int(os.environ["OMP_NUM_THREADS"]))
  ```
- [ ] **Task 2.10.2**: Set a reasonable default (e.g. 2 threads) if `cpu_count()` is unavailable.

#### Testing
- `tests/test_tts_engines/test_pocket_engine.py`: Verify `torch.get_num_threads()` returns expected value after engine init.

---

### Feature 2.11: Partial Async I/O Migration (Issue #16, first pass)

**As a** developer,
**I want** the most critical blocking I/O call (HTTP fetch in worker) offloaded to a thread pool,
**So that** the event loop can respond to shutdown signals and process other bookmarks during long requests.

#### Tasks
- [ ] **Task 2.11.1**: In `backend/worker.py:process_bookmark_pipeline_worker()`, wrap the sync `extract_article_content()` call in `asyncio.to_thread()`:
  ```python
  clean_text = await asyncio.to_thread(extract_article_content, bookmark.url)
  ```

#### Testing
- `tests/test_worker.py`: Mock `extract_article_content` to take 5 seconds, verify worker still responds to shutdown signal during the call.

---

### Wave 2 Verification
```bash
python -m pytest tests/ -v -k "test_rate_limit or test_csrf or test_exception or test_wal or test_index or test_bulk_settings or test_torch_threads or test_async_offload"
```

---

## Wave 3 — Moderate Security + Performance (P2)

Addresses remaining issues with moderate security impact or performance gains.

### Section A — Security (P2)

---

### Feature 3.1: Remove Partial Token from Logs (Issue #11)

**As a** security-conscious developer,
**I want** no part of the API token to ever appear in logs,
**So that** an attacker with log access cannot reduce the effective keyspace.

#### Tasks
- [ ] **Task 3.1.1**: In `backend/syncer.py:34-35`, replace:
  ```python
  logger.info(f"API Token loaded successfully. Length: {len(token)} chars")
  ```
  Remove the masked token display entirely. Log only that the token is configured.

#### Testing
- `tests/test_syncer.py`: Capture log output, verify no token characters (even masked) appear in log messages.

---

### Feature 3.2: Fix Instapaper RSS GUID Collision (Issue #12)

**As a** podcast subscriber,
**I want** each Instapaper bookmark episode to have a unique GUID in the RSS feed,
**So that** my podcast app does not show all Instapaper episodes as a single entry.

#### Tasks
- [ ] **Task 3.2.1**: In `backend/rss_generator.py:86`, change GUID generation:
  ```python
  guid = item.raindrop_id or item.instapaper_id or item.id
  xml.append(f'      <guid isPermaLink="false">VibeListen_{guid}</guid>')
  ```

#### Testing
- `tests/test_rss_generator.py`: Generate RSS with both Raindrop and Instapaper bookmarks. Verify each `<guid>` is unique. No `<guid>VibeListen_None</guid>` appears.

---

### Feature 3.3: Move Signal Handler Registration Inside `run_worker()` (Issue #13)

**As a** developer,
**I want** signal handlers registered only when the worker process runs,
**So that** importing the module in tests or from the FastAPI process does not install handlers in the parent process.

#### Tasks
- [ ] **Task 3.3.1**: In `backend/worker.py`, remove lines 26-27 (top-level signal registration).
- [ ] **Task 3.3.2**: Move them to the top of `run_worker()`:
  ```python
  async def run_worker(poll_interval: float = 2.0) -> None:
      signal.signal(signal.SIGINT, _handle_signal)
      signal.signal(signal.SIGTERM, _handle_signal)
      ...
  ```

#### Testing
- `tests/test_worker.py`: Import the module and verify no signal handlers are registered for SIGINT/SIGTERM. Call `run_worker()` briefly and verify handlers are registered.

---

### Feature 3.4: Redact Secrets in Settings API (Issue #14)

**As a** server operator,
**I want** `GET /api/settings` to never return secret values,
**So that** a client-side compromise or XSS cannot steal credentials.

#### Tasks
- [ ] **Task 3.4.1**: In `backend/main.py:get_all_settings()`, apply the `secret_redactor()` from Feature 0.3 to any value whose key matches `REDACTED_SECRET_KEYS`:
  ```python
  from backend.auth import secret_redactor, REDACTED_SECRET_KEYS
  
  for s in settings:
      if any(secret_kw in s.key.lower() for secret_kw in REDACTED_SECRET_KEYS):
          s.value = secret_redactor(s.value)
  ```

#### Testing
- `tests/test_main.py`: Set a secret key (e.g. `raindrop_token = "my-secret"`), call `GET /api/settings`, verify response contains `"***REDACTED***"` for that key.

---

### Feature 3.5: Fix Stored XSS via Domain Field (Issue #15)

**As a** user,
**I want** the bookmark domain field to be HTML-escaped before rendering in the dashboard,
**So that** a malicious domain from a bookmark cannot execute JavaScript.

#### Tasks
- [ ] **Task 3.5.1**: In `frontend/app.js:266`, change:
  ```javascript
  <span class="card-domain">${escapeHTML(b.domain)}</span>
  ```

#### Testing
- Frontend test: Verify that a bookmark with domain `<img src=x onerror=alert(1)>` renders as escaped text, not as an active HTML element.

---

### Section B — Performance (P2)

---

### Feature 3.6: Increase Poll Interval When Idle (Issue #21)

**As a** developer,
**I want** the worker to poll less frequently when no work is queued,
**So that** unnecessary DB queries are reduced (~43k/day → ~8.6k/day with 10s idle interval).

#### Tasks
- [ ] **Task 3.6.1**: In `backend/worker.py:run_worker()`, implement adaptive polling:
  ```python
  consecutive_idle = 0
  while not _shutdown_requested:
      ...
      if bookmark:
          consecutive_idle = 0
      else:
          consecutive_idle += 1
          sleep_time = min(poll_interval * (1.5 ** min(consecutive_idle, 5)), 30.0)
          await asyncio.sleep(sleep_time)
  ```

#### Testing
- `tests/test_worker.py`: Mock `claim_next_bookmark` to return `None` repeatedly, verify sleep interval increases. Mock it to return a bookmark after idle, verify interval resets.

---

### Feature 3.7: Single Commit in `reset_stalled_bookmarks` (Issue #22)

**As a** developer,
**I want** `reset_stalled_bookmarks()` to use a single commit instead of three,
**So that** unnecessary transaction overhead is eliminated.

#### Tasks
- [ ] **Task 3.7.1**: In `backend/worker.py:37-49`, remove `session.commit()` from inside the loop and add one after the loop:
  ```python
  def reset_stalled_bookmarks(session: Session) -> int:
      reset_count = 0
      for status in ["processing", "parsing", "synthesizing"]:
          statement = select(Bookmark).where(Bookmark.status == status)
          stalled = session.exec(statement).all()
          for bookmark in stalled:
              bookmark.status = "queued"
              session.add(bookmark)
              reset_count += 1
      if reset_count:
          session.commit()
      return reset_count
  ```

#### Testing
- `tests/test_worker.py`: Create bookmarks in all three stalled states, call `reset_stalled_bookmarks`, verify all are reset and exactly 1 commit occurs.

---

### Feature 3.8: Accurate MP3 Duration (Issue #23)

**As a** listener,
**I want** the audio duration displayed in the dashboard and RSS feed to be accurate,
**So that** I know the actual length of each podcast episode.

#### Tasks
- [ ] **Task 3.8.1**: In `backend/tts_engines/edge_engine.py:67`, replace the magic-number estimate:
  ```python
  from mutagen.mp3 import MP3
  audio = MP3(output_path)
  duration = audio.info.length
  ```
- [ ] **Task 3.8.2**: Handle case where mutagen is unavailable (fallback to filesize estimate).

#### Testing
- `tests/test_tts_engines/test_edge_engine.py`: Create a small known-duration MP3 file, verify the returned duration matches within 5%.

---

### Feature 3.9: Single Connection Edge TTS (Issue #24)

**As a** developer,
**I want** Edge TTS to use a single `Communicate` connection for the entire article,
**So that** we avoid unnecessary HTTPS/SSE connection overhead per chunk.

#### Tasks
- [ ] **Task 3.9.1**: Investigate if `edge_tts.Communicate` handles long text natively (check `edge-tts` version in use).
- [ ] **Task 3.9.2**: If supported, remove chunking logic entirely from `edge_engine.py` and pass the full text as a single call.

#### Testing
- `tests/test_tts_engines/test_edge_engine.py`: Synthesize a long text, verify output is complete and well-formed MP3. Compare number of HTTP connections (before/after).

---

### Feature 3.10: Engine Returns Actual Output Path (Issue #25)

**As a** developer,
**I want** each TTS engine to return its actual output path in the result dict,
**So that** the worker does not need to guess the file extension.

#### Tasks
- [ ] **Task 3.10.1**: Update `BaseTTSEngine.synthesize()` return type hint to include `"output_path": str` in the dict.
- [ ] **Task 3.10.2**: Update each engine to return `output_path`:
  - `EdgeEngine`: returns the original `output_path` (always `.mp3`).
  - `PiperEngine`: returns the `.wav` path it actually writes to.
  - `PocketEngine`: returns the `.wav` path it actually writes to.
- [ ] **Task 3.10.3**: In `backend/worker.py:142-147`, replace the fragile `.mp3` → `.wav` fallback with:
  ```python
  filename = Path(stats["output_path"]).name
  ```

#### Testing
- `tests/test_worker.py`: Mock each engine to return its respective output path, verify worker records the correct filename.

---

### Feature 3.11: Targeted DOM Updates (Issue #26)

**As a** user,
**I want** the dashboard to update only changed bookmark cards during polling,
**So that** the UI does not jank and flash on every 3-second poll.

#### Tasks
- [ ] **Task 3.11.1**: In `frontend/app.js`, refactor `fetchBookmarks()` to use a diff-based approach:
  - Maintain a map of `id -> DOM element` reference.
  - On poll, compare incoming data with existing `bookmarks` array.
  - Only create elements for new bookmarks, update changed status/duration elements in-place, remove elements for deleted bookmarks.
- [ ] **Task 3.11.2**: Increase poll interval from 3s to 5s.

#### Testing
- Manual verification: Open browser DevTools, observe DOM mutations during polling — only changed card elements should be updated.

---

### Feature 3.12: Piper Engine Thread Safety (Issue #27)

**As a** developer,
**I want** the `_get_voice()` method to be thread-safe,
**So that** concurrent calls for an uncached voice do not race on `PiperVoice.load()`.

#### Tasks
- [ ] **Task 3.12.1**: In `backend/tts_engines/piper_engine.py`, add a `threading.Lock`:
  ```python
  def __init__(self):
      ...
      self._voice_cache: Dict[str, PiperVoice] = {}
      self._voice_lock = threading.Lock()
  
  def _get_voice(self, voice_name: str) -> PiperVoice:
      if voice_name in self._voice_cache:
          return self._voice_cache[voice_name]
      with self._voice_lock:
          # Double-check after acquiring lock
          if voice_name in self._voice_cache:
              return self._voice_cache[voice_name]
          ...  # load and cache
  ```

#### Testing
- `tests/test_tts_engines/test_piper_engine.py`: Launch multiple threads simultaneously requesting the same uncached voice, verify `PiperVoice.load()` is called only once.

---

### Feature 3.13: Pocket Cache Thread Safety (Issue #28)

**As a** developer,
**I want** the `_VOICES_CACHE` global to be thread-safe,
**So that** two threads do not race on the HF API call and cache write.

#### Tasks
- [ ] **Task 3.13.1**: In `backend/tts_engines/pocket_engine.py`, add a module-level lock:
  ```python
  _VOICES_CACHE_LOCK = threading.Lock()
  
  def _available_voices(self) -> list[str]:
      global _VOICES_CACHE, _VOICES_CACHE_TIME
      now = time.monotonic()
      if _VOICES_CACHE is not None and (now - _VOICES_CACHE_TIME) < _VOICES_CACHE_TTL:
          return _VOICES_CACHE
      with _VOICES_CACHE_LOCK:
          # Double-check
          if _VOICES_CACHE is not None and (now - _VOICES_CACHE_TIME) < _VOICES_CACHE_TTL:
              return _VOICES_CACHE
          ...  # fetch and cache
  ```

#### Testing
- `tests/test_tts_engines/test_pocket_engine.py`: Mock `list_repo_files`, launch concurrent threads calling `_available_voices()`, verify `list_repo_files` is called only once.

---

### Feature 3.14: Separate Connect and Read Timeouts (Issue #29)

**As a** developer,
**I want** separate connect and read timeouts for HTTP requests,
**So that** a slow server sending 1 byte/sec cannot keep the connection open indefinitely.

#### Tasks
- [ ] **Task 3.14.1**: In `backend/parser.py:23`, change:
  ```python
  response = requests.get(url, headers=headers, timeout=(10, 30))
  ```

#### Testing
- `tests/test_parser.py`: Mock a slow response (1 byte/sec), verify the read timeout fires after 30s (not 15s of combined timeout).

---

### Feature 3.15: Retry Logic for External API Calls (Issue #30)

**As a** user,
**I want** transient network failures during sync to be retried automatically,
**So that** a brief network blip does not fail the entire sync operation.

#### Tasks
- [ ] **Task 3.15.1**: Add `tenacity` retry decorator to `sync_raindrops()` HTTP call:
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
  
  @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(requests.RequestException))
  def _raindrop_api_call(url, headers, params):
      response = requests.get(url, headers=headers, params=params, timeout=10)
      response.raise_for_status()
      return response
  ```
- [ ] **Task 3.15.2**: Apply same pattern to Instapaper API calls in `sync_instapaper()`.
- [ ] **Task 3.15.3**: Apply same pattern to `extract_article_content()` HTTP fetch in `parser.py`.

#### Testing
- `tests/test_syncer.py`: Mock HTTP to fail twice then succeed, verify the sync completes after retries.

---

### Feature 3.16: Offload HuggingFace Network Calls (Issue #31)

**As a** developer,
**I want** HuggingFace network calls in PocketEngine to run in a thread pool,
**So that** the async worker does not freeze during model download or voice listing.

#### Tasks
- [ ] **Task 3.16.1**: In `backend/tts_engines/pocket_engine.py:_available_voices()`, wrap `list_repo_files()` in `asyncio.to_thread()`:
  (Note: This method is called from sync context currently — since it's called by `synthesize()` which is async, we can use `await asyncio.to_thread(...)`)
- [ ] **Task 3.16.2**: In `_voice_to_path()`, wrap `hf_hub_download()` in `asyncio.to_thread()`.
- [ ] **Task 3.16.3**: Make `_available_voices()` and `_voice_to_path()` async-aware.

#### Testing
- `tests/test_tts_engines/test_pocket_engine.py`: Mock `list_repo_files` and `hf_hub_download` to have delays, verify they run off the main thread.

---

### Feature 3.17: Full Async I/O Migration (Issue #16, second pass)

**As a** developer,
**I want** all blocking I/O in the async code paths to use async libraries or thread pools,
**So that** the event loop is never blocked during long operations.

#### Tasks
- [ ] **Task 3.17.1**: Replace `requests.get()` in `backend/parser.py` with `httpx.AsyncClient`.
- [ ] **Task 3.17.2**: Replace sync file writes in all TTS engines with `aiofiles.open()`.
- [ ] **Task 3.17.3**: Replace sync `wave.open()` in Piper/Pocket with async wrappers or thread pool offload.
- [ ] **Task 3.17.4**: Replace `requests` calls in `backend/syncer.py` with `httpx.AsyncClient`.
- [ ] **Task 3.17.5**: Evaluate `aiosqlite` for database sessions (lowest priority — WAL mode from Feature 2.6 already mitigates most contention).

#### Testing
- Run full test suite. Verify no regression in TTS output quality.
- Load-test with concurrent requests, verify no `RuntimeError: Timeout context manager should be used inside a task` or event-loop blocking errors.

---

### Wave 3 Verification
```bash
python -m pytest tests/ -v
```

---

## Wave 4 — Code Quality Nits (P3)

Low-priority improvements that improve maintainability and correctness.

---

### Feature 4.1: Refactor Raw SQL Migration (Issue #32)

**As a** developer,
**I want** database migrations to use SQLModel/SQLAlchemy primitives instead of raw `sqlite3`,
**So that** the migration is type-safe and works across different database backends if needed.

#### Tasks
- [ ] **Task 4.1.1**: Refactor `migrate_database()` in `backend/database.py` to use SQLAlchemy's `inspect()` and `Table` operations.

#### Testing
- `tests/test_database.py`: Run migration against an existing database, verify expected columns/indexes exist.

---

### Feature 4.2: Remove Duplicate Import (Issue #33)

**As a** developer,
**I want** no duplicate imports in the codebase,
**So that** the code is clean and linters pass without warnings.

#### Tasks
- [ ] **Task 4.2.1**: In `backend/main.py:6-7`, remove the duplicate `from contextlib import asynccontextmanager` line.

#### Testing
- Visual inspection. Lint check.

---

### Feature 4.3: Document or Adjust Python Syntax (Issue #34)

**As a** developer,
**I want** the minimum Python version documented or the code adjusted for compatibility,
**So that** users know what Python version is required.

#### Tasks
- [ ] **Task 4.3.1**: Add `python_requires = ">= 3.10"` to `setup.cfg` or `pyproject.toml` (or document in README).
- [ ] **Task 4.3.2**: Alternatively, add `from __future__ import annotations` to `pocket_engine.py` for older Python compatibility.

#### Testing
- Verify code runs on Python 3.10+.

---

### Feature 4.4: Refactor RSS Builder (Issue #35)

**As a** developer,
**I want** RSS XML constructed using `xml.etree.ElementTree` instead of manual string concatenation,
**So that** XML escaping is correct and robust against special characters.

#### Tasks
- [ ] **Task 4.4.1**: Rewrite `generate_podcast_rss()` in `backend/rss_generator.py` to build the XML document using `xml.etree.ElementTree`:
  - Create `ElementTree` elements for each RSS node.
  - Use `SubElement` for nested elements.
  - Serialize with `ET.tostring(xml_declaration=True, encoding="UTF-8")`.
- [ ] **Task 4.4.2**: Ensure iTunes namespace is handled correctly (`{http://www.itunes.com/dtds/podcast-1.0.dtd}tag`).
- [ ] **Task 4.4.3**: Remove unused `import xml.etree.ElementTree as ET` — it will now be used.

#### Testing
- `tests/test_rss_generator.py`: Generate RSS with bookmarks containing special characters in title/author (quotes, ampersands, angle brackets). Verify the output XML is well-formed and attributes are correctly escaped. Validate with `xml.etree.ElementTree.fromstring()`.

---

### Wave 4 Verification
```bash
python -m pytest tests/ -v
# Also manually check:
python -c "import xml.etree.ElementTree as ET; ET.fromstring(open('/tmp/test_rss.xml').read())"
```

---

## Cross-Cutting Concerns

### Database Migration Strategy

- All schema changes (index additions, column changes) go through `migrate_database()` in `backend/database.py` for existing databases.
- New installations get the correct schema via `SQLModel.metadata.create_all()`.
- Wave 0 runs first to ensure `SECRET_KEY` and dependencies are available.
- The credential encryption (Feature 1.3) includes a migration helper to encrypt existing plaintext secrets on first startup.

### Frontend-Backend Compatibility

- Wave 1 (API Key auth) requires frontend changes — ensure the dashboard still works without the key for the public endpoints.
- Wave 2 (Bulk settings API) deprecates but keeps the old single-setting endpoint.
- Wave 3 (DOM diffing) is purely frontend and should be transparent to the backend.

### Rollback Strategy

- Each feature is designed to be independently revertible.
- Database schema changes are additive (new indexes, new columns) — no destructive operations.
- Credential encryption is transparent to the application logic: `get_setting` and `set_setting` handle encryption/decryption internally.

---

## Rollup Effort Estimate

| Wave | Features | Tasks | Est. Effort |
|------|----------|-------|-------------|
| Wave 0 | 3 | 6 | ~30 min |
| Wave 1 | 7 | ~18 | ~4 hours |
| Wave 2 | 11 | ~25 | ~5 hours |
| Wave 3 | 17 | ~30 | ~6 hours |
| Wave 4 | 4 | ~6 | ~1 hour |
| **Total** | **42** | **~85** | **~16.5 hours** |

## Testing Summary

| Test File | Features Covered | New/Existing |
|-----------|-----------------|--------------|
| `tests/test_auth.py` | 0.3, 1.2, 1.3 | New |
| `tests/test_main.py` | 1.2, 1.4, 1.5, 1.6, 1.7, 2.2, 2.3, 2.4, 2.5, 2.9, 3.4 | Expand existing |
| `tests/test_parser.py` | 1.1, 3.14, 3.15 | Expand existing |
| `tests/test_database.py` | 2.6, 2.7, 4.1 | Expand existing |
| `tests/test_syncer.py` | 2.8, 3.1, 3.15 | Expand existing |
| `tests/test_worker.py` | 2.1, 2.11, 3.3, 3.6, 3.7, 3.10 | New |
| `tests/test_rss_generator.py` | 3.2, 4.4 | Expand existing |
| `tests/test_tts_engines/test_edge_engine.py` | 3.8, 3.9 | Expand existing |
| `tests/test_tts_engines/test_piper_engine.py` | 3.12 | New |
| `tests/test_tts_engines/test_pocket_engine.py` | 2.10, 3.13, 3.16 | New |
