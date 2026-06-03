# Phase 3 Agile Implementation Plan: Instapaper Integration & UI Settings Dashboard

This implementation plan is organized using the **Agile Framework**. The scope of Phase 3 is broken down into **Features (Epics)**, **User Stories**, and actionable **Tasks** with specific **Acceptance Criteria**.

---

## 📋 Epic/Feature 1: Pluggable Read-it-Later Database Architecture & DB Migration

### 👤 User Story 1.1 (Safe Schema Evolution)
> **As a** VibeListen user,
> **I want** the SQLite database schema to automatically support both Instapaper and Raindrop bookmarks,
> **So that** I can switch or combine read-it-later providers without losing my existing generated audio links or corrupting my current database.

#### 🛠️ Tasks
- [ ] **Task 1.1.1 (Model Update)**: Modify the `Bookmark` SQLModel in `backend/database.py`.
  - Make `raindrop_id` optional and nullable: `raindrop_id: Optional[int] = Field(default=None, unique=True, index=True, nullable=True)`.
  - Add `instapaper_id: Optional[int] = Field(default=None, unique=True, index=True, nullable=True)`.
  - Add `service: str = Field(default="raindrop", index=True)` to track bookmark origin dynamically.
- [ ] **Task 1.1.2 (Self-Healing Migration)**: Implement `migrate_database()` in `backend/database.py` and run it on server initialization inside `init_db()`.
  - Use standard `sqlite3` to check if `instapaper_id` and `service` columns exist.
  - Execute `ALTER TABLE bookmark ADD COLUMN instapaper_id INTEGER` and `ALTER TABLE bookmark ADD COLUMN service VARCHAR DEFAULT 'raindrop'` if missing.
  - Create a unique index on `instapaper_id`.
- [ ] **Task 1.1.3 (Dynamic Filename Mapping)**: Adjust `backend/worker.py` audio synthesis filename selection:
  ```python
  if bookmark.raindrop_id:
      filename = f"raindrop_{bookmark.raindrop_id}.mp3"
  else:
      filename = f"instapaper_{bookmark.instapaper_id}.mp3"
  ```

#### 🎯 Acceptance Criteria
- Starting the server on a database that already has bookmarks is 100% backward-compatible (no crashes, no missing column errors).
- New Instapaper bookmarks can be saved with `raindrop_id = NULL` and an active `instapaper_id` value without unique constraint conflicts.
- Existing Raindrop bookmarks retain their original generated audio file paths and play correctly.

---

## 📋 Epic/Feature 2: Instapaper OAuth 1.0a xAuth & Synchronization Service

### 👤 User Story 2.1 (Secure Credentials Exchange & Syncing)
> **As a** user,
> **I want** the backend to securely authenticate with Instapaper using xAuth (exchanging email/password directly for a permanent API token) and sync my unread library,
> **So that** I don't have to deal with complex browser redirect authorization flows and can sync my bookmarks automatically.

#### 🛠️ Tasks
- [ ] **Task 2.1.1 (Dependency Management)**: Add `requests-oauthlib>=1.3.0` to [requirements.txt](file:///home/sean/Coding%20Projects/ReadItLaterPodcast/VibeListen/requirements.txt).
- [ ] **Task 2.1.2 (Pluggable Dispatcher)**: Implement `sync_bookmarks(session: Session, limit: int = 50) -> int` dispatcher in `backend/syncer.py` that reads the `bookmark_provider` setting (defaulting to Raindrop) and routes execution.
- [ ] **Task 2.1.3 (xAuth Client Engine)**: Implement `sync_instapaper(session: Session, limit: int = 50) -> int` in `backend/syncer.py`:
  - Check if permanent OAuth tokens are cached in the SQLite `Setting` table.
  - If not cached, trigger a POST to `https://www.instapaper.com/api/1/oauth/access_token` signed via `requests_oauthlib.OAuth1` using `Consumer Key` and `Consumer Secret` with user's username & password.
  - Parse form-encoded tokens, cache `oauth_token` and `oauth_token_secret` in the `Setting` table, and immediately discard the plaintext password for security.
  - Query `https://www.instapaper.com/api/1.1/bookmarks/list` using the authenticated OAuth session.
  - Parse array items of `type == "bookmark"`, mapping `bookmark_id`, `url`, `title`, and excerpt text, then upsert new records in SQLite.
- [ ] **Task 2.1.4 (API Refactor)**: Modify `trigger_sync` in `backend/main.py` to execute `sync_bookmarks(db)` instead of the hardcoded `sync_raindrops(db)`.

#### 🎯 Acceptance Criteria
- Exchanging credentials via xAuth works seamlessly, returning a valid, cached permanent token.
- Bookmarks are synced correctly, duplicates are safely skipped, and errors (such as bad credentials) are propagated to the frontend cleanly.
- Pluggable routing correctly runs Raindrop sync when provider is `raindrop`, and Instapaper sync when provider is `instapaper`.

---

## 📋 Epic/Feature 3: Sleek Interactive Library Settings Dashboard

### 👤 User Story 3.1 (UI Credentials Manager & Visual Badges)
> **As a** self-hosting user,
> **I want** a unified Settings Modal in my web dashboard with separate tabs for speech settings and bookmark source settings,
> **So that** I can easily toggle providers and enter my API keys/credentials directly in the UI.

#### 🛠️ Tasks
- [ ] **Task 3.1.1 (Multi-Tab UI Panel)**: Update `frontend/index.html` to convert the settings modal into a beautiful two-tab navigation glass panel:
  - **Tab A: Speech Settings**: Speeches, default voice selection, voice cloning WAV upload.
  - **Tab B: Library Integration**: Service selection dropdown (Raindrop.io vs. Instapaper) with dynamic, toggleable form fields:
    - Raindrop fields: Token.
    - Instapaper fields: Consumer Key, Consumer Secret, Email/Username, Password.
- [ ] **Task 3.1.2 (Dashboard badge additions)**: Modify `app.js` to render a sleek, HSL-colored visual badge (e.g. `Instapaper` or `Raindrop.io`) on the bottom metadata strip of every bookmark card.
- [ ] **Task 3.1.3 (Credentials Saving & Verification JS)**: Write JS saves/loads for credentials in `frontend/app.js`:
  - Request `GET /api/settings` to populate input fields on open.
  - On Save, trigger `POST /api/settings` for the selected service keys, showing real-time feedback.
  - If Instapaper is active, trigger an immediate dry-run authentication sync to verify credentials and report success/failure using a toast notification.
- [ ] **Task 3.1.4 (Dynamic UX Text)**: Make empty state instructions dynamically mention the active provider (e.g. "Run Sync Library to import your bookmarks from Instapaper").

#### 🎯 Acceptance Criteria
- Settings modal renders in modern glassmorphism aesthetic with tabs that switch layout states smoothly.
- Selecting a provider instantly hides the irrelevant fields and shows the appropriate inputs.
- Saving new settings immediately validates the credentials and displays a beautiful success or detailed error toast message.
- Bookmark cards correctly display unified badges indicating where each article originated.

---

## 🧪 Verification Plan

### Automated Tests
- Implement `tests/test_instapaper.py` using `pytest`.
- Mock oauth access token responses and bookmark listing JSON.
- Verify migration script runs cleanly against existing SQLite DB schema mockups.

### Manual Verification
- Verify setting tab rendering on mobile and desktop layout views.
- Try authenticating with bad username/password to ensure validation handles failures gracefully.
- Perform a complete end-to-end sync, parse, audio compile, and podcast subscription flow with genuine Instapaper bookmark feeds.
