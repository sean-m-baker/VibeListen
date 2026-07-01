# VibeListen Codebase Security and Performance Audit Report

This report presents a thorough security and performance audit of the VibeListen codebase. While recent refactoring successfully addressed many basic issues, a deep-dive analysis reveals several advanced architectural security vulnerabilities and performance optimization opportunities.

---

## 1. Security Findings

### 1.1. DNS Rebinding via SSRF Time-of-Check to Time-of-Use (TOCTOU)
* **Location:** `backend/parser.py` (specifically `_validate_url` and `extract_article_content`) and `backend/auth.py` (`is_internal_ip`)
* **Severity:** **High**
* **Vulnerability:**
  The `is_internal_ip` function resolves the hostname using `socket.getaddrinfo`. If it resolves to a public IP, the parser proceeds to call `requests.get(url, ...)`. 
  Because `requests.get` executes its own separate DNS resolution step, an attacker can exploit a TOCTOU race condition (DNS Rebinding) by configuring a custom nameserver. The nameserver can return a safe public IP during the first resolution check, and then return a private IP (e.g., `127.0.0.1` or `169.254.169.254` cloud metadata services) during the second resolution inside `requests.get`.
* **Impact:** An attacker can bypass the internal IP blocklist and perform Server-Side Request Forgery (SSRF) against internal ports, database interfaces, or cloud metadata endpoints.
* **Recommended Mitigation:**
  Resolve the hostname once, check if the resolved IP address is internal, and then perform the HTTP request directly to that resolved IP address. Override the host header in the request to maintain virtual hosting compatibility:
  ```python
  # Resolve domain once
  resolved_ip = socket.getaddrinfo(parsed.hostname, ...)[0][4][0]
  # Perform request directly to IP, keeping Host header
  response = requests.get(f"{parsed.scheme}://{resolved_ip}{parsed.path}", headers={"Host": parsed.hostname}, ...)
  ```

### 1.2. Transcoding Denial of Service (DoS) via Dynamic ffmpeg Spawning
* **Location:** `backend/main.py` (`serve_rss_audio` endpoint)
* **Severity:** **Medium**
* **Vulnerability:**
  The `/rss-audio/{filename:path}` endpoint does not require API key authentication (to support standard podcast app downloads). If the cached MP3 file does not exist, the endpoint spawns a separate `ffmpeg` subprocess via `asyncio.create_subprocess_exec` to transcode the source WAV to MP3 on-the-fly.
* **Impact:** An unauthenticated attacker can query this endpoint repeatedly with different filenames or trigger concurrent requests, flooding the host CPU with resource-heavy `ffmpeg` transcoding tasks. This will lead to complete CPU exhaustion and denial of service for the main web server.
* **Recommended Mitigation:**
  1. Offload WAV-to-MP3 transcoding to the background worker loop immediately after speech generation completes, instead of doing it lazily on-demand in the HTTP thread.
  2. Serve only pre-rendered static MP3 files from the cache directory and completely disable dynamic subprocess spawning on the client-facing route.

### 1.3. Cryptographic Risk: Shared Key for Web Auth & Credential Encryption
* **Location:** `backend/config.py` and `backend/auth.py`
* **Severity:** **Medium**
* **Vulnerability:**
  The application utilizes a single `SECRET_KEY` for two distinct, critical purposes:
  1. As the API key (`X-API-Key`) sent by the frontend in plain text headers to authenticate operations.
  2. As the symmetric Fernet key used to encrypt and decrypt sensitive database credentials (e.g., Raindrop and Instapaper tokens).
  Additionally, the launcher injects this exact key into the HTML DOM as a meta tag `<meta name="api-key" content="...">` to authenticate client-side requests.
* **Impact:** 
  Since the key is embedded directly in client-side HTML, any Cross-Site Scripting (XSS) vulnerability, proxy exposure, or local storage compromise directly reveals the cryptographic key. An attacker possessing this key can not only authenticate as the administrator but can also fully decrypt all third-party integration tokens stored in the database.
* **Recommended Mitigation:**
  Separate the concerns:
  1. Generate a distinct, randomly generated cryptographic key (e.g., `ENCRYPTION_KEY`) that remains strictly server-side and is never exposed to the client.
  2. Use a separate API key or session token mechanism for frontend authentication.

### 1.4. Missing Parameter Validation in Settings Routes
* **Location:** `backend/main.py` (`update_setting` and `bulk_update_settings`)
* **Severity:** **Low**
* **Vulnerability:**
  The routes accept arbitrary key-value parameters and save them straight to the `Setting` table. There are no size checks on the input string length or restrictions on what sections/keys can be registered.
* **Impact:** Database bloating or potential logic manipulation if system-critical values are modified or injected.
* **Recommended Mitigation:**
  Implement strict schema validation (using Pydantic models) to allow updates only to a pre-defined set of configuration keys (e.g., `sync_service`, `audio_bitrate`, `max_rss_items`).

---

## 2. Performance Findings

### 2.1. Lack of HTTP Connection Pooling (TCP/TLS Handshake Overhead)
* **Location:** `backend/parser.py` and `backend/syncer.py`
* **Severity:** **Low**
* **Issue:**
  The code initiates individual network requests using standalone calls such as `requests.get` and `requests.post`. This forces the client to open a new TCP connection and perform a full TLS handshake for every single read-it-later bookmark synced or web article parsed.
* **Impact:** Increased network latency and CPU overhead, especially when syncing dozens of bookmarks sequentially.
* **Recommended Mitigation:**
  Instantiate and reuse a `requests.Session` object across sync operations. This enables HTTP Keep-Alive, allowing TCP connections to be pooled and reused.

### 2.2. Heavy Synchronous Code inside Thread Offloads
* **Location:** `backend/tts_engines/pocket_engine.py`
* **Severity:** **Low**
* **Issue:**
  During Pocket TTS synthesis, PyTorch models run inference via `self._tts.simple_generate(...)` which is a CPU/GPU intensive operation. The code restricts PyTorch core utilisation via `torch.set_num_threads()`. However, the synthesis itself runs synchronously within the worker process thread.
* **Impact:** While the worker is processing an article, no other bookmarks can be processed (single-threaded sequence).
* **Recommended Mitigation:**
  Transition the worker pipeline to support concurrent processing of queued tasks, using a process pool or distributed task workers if scaling is required.
