/* ==========================================================================
   VibeListen Frontend - State Management & API Connections
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // Application State
    let bookmarks = [];
    let currentFilter = "all";
    let searchQuery = "";
    let pollingInterval = null;

    // DOM Elements
    const btnSync = document.getElementById("btn-sync");
    const btnRss = document.getElementById("btn-rss");
    const btnModalClose = document.getElementById("btn-modal-close");
    const modalRss = document.getElementById("modal-rss");
    const rssUrlInput = document.getElementById("rss-url-input");
    const btnCopyRss = document.getElementById("btn-copy-rss");
    const searchInput = document.getElementById("search-input");
    const tabBtns = document.querySelectorAll(".tab-btn");
    const bookmarksGrid = document.getElementById("bookmarks-grid");
    const emptyState = document.getElementById("empty-state");
    const toastContainer = document.getElementById("toast-container");

    // Stats Elements & Cards
    const countPending = document.getElementById("count-pending");
    const countActive = document.getElementById("count-active");
    const countCompleted = document.getElementById("count-completed");
    const statPending = document.getElementById("stat-pending");
    const statActive = document.getElementById("stat-active");
    const statCompleted = document.getElementById("stat-completed");

    // ----------------- Core API Requests -----------------

    async function fetchBookmarks(silent = false) {
        try {
            const response = await fetch("/api/bookmarks");
            if (!response.ok) throw new Error("Network response was not ok");
            bookmarks = await response.json();
            renderStats();
            renderBookmarks();
            checkAndSetupPolling();
        } catch (error) {
            console.error("Error fetching bookmarks:", error);
            if (!silent) showToast("❌ Failed to load bookmarks from server.", "error");
        }
    }

    async function syncLibrary() {
        btnSync.disabled = true;
        const icon = btnSync.querySelector("svg");
        icon.classList.add("spin");
        showToast("🔄 Syncing library with Raindrop.io...");

        try {
            const response = await fetch("/api/sync", { method: "POST" });
            const data = await response.json();
            if (response.ok && data.status === "success") {
                const count = data.new_bookmarks_count;
                if (count > 0) {
                    showToast(`✅ Synced! Found ${count} new bookmarks.`, "success");
                } else {
                    showToast("ℹ️ Synced. Your library is already up to date.", "info");
                }
                await fetchBookmarks();
            } else {
                throw new Error(data.detail || "Sync failed");
            }
        } catch (error) {
            console.error("Sync error:", error);
            showToast(`❌ Sync failed: ${error.message}`, "error");
        } finally {
            btnSync.disabled = false;
            icon.classList.remove("spin");
        }
    }

    async function triggerGeneration(id) {
        showToast("Queuing article for speech generation...");
        try {
            const response = await fetch(`/api/generate/${id}`, { method: "POST" });
            const data = await response.json();
            if (response.ok) {
                showToast("⚡ Article is now in the compilation queue!", "success");
                await fetchBookmarks();
            } else {
                throw new Error(data.detail || "Queueing failed");
            }
        } catch (error) {
            console.error("Generation error:", error);
            showToast(`❌ Failed to trigger compilation: ${error.message}`, "error");
        }
    }

    // ----------------- Dynamic Rendering & UI -----------------

    function renderStats() {
        const stats = {
            pending: 0,
            active: 0,
            completed: 0
        };

        bookmarks.forEach(b => {
            if (b.status === "completed") {
                stats.completed++;
            } else if (["queued", "parsing", "synthesizing"].includes(b.status)) {
                stats.active++;
            } else {
                stats.pending++;
            }
        });

        countPending.textContent = stats.pending;
        countActive.textContent = stats.active;
        countCompleted.textContent = stats.completed;
    }

    function updateFilterUI() {
        // Update active class on tab buttons
        tabBtns.forEach(btn => {
            if (btn.getAttribute("data-filter") === currentFilter) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        // Update active class on stat cards to show interactive focus
        if (statPending) {
            if (currentFilter === "pending") {
                statPending.classList.add("active");
            } else {
                statPending.classList.remove("active");
            }
        }
        if (statActive) {
            if (currentFilter === "active") {
                statActive.classList.add("active");
            } else {
                statActive.classList.remove("active");
            }
        }
        if (statCompleted) {
            if (currentFilter === "completed") {
                statCompleted.classList.add("active");
            } else {
                statCompleted.classList.remove("active");
            }
        }
    }

    function renderBookmarks() {
        bookmarksGrid.innerHTML = "";

        // Sync active state across tab buttons and stats cards
        updateFilterUI();

        // Filter bookmarks by Search & Tab Status
        const filtered = bookmarks.filter(b => {
            // Search Query
            const matchesSearch =
                b.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                (b.author && b.author.toLowerCase().includes(searchQuery.toLowerCase())) ||
                b.domain.toLowerCase().includes(searchQuery.toLowerCase());

            if (!matchesSearch) return false;

            // Tab Filter
            if (currentFilter === "all") return true;
            if (currentFilter === "completed") return b.status === "completed";
            if (currentFilter === "active") return ["queued", "parsing", "synthesizing"].includes(b.status);
            if (currentFilter === "pending") return !["completed", "queued", "parsing", "synthesizing"].includes(b.status);
            return true;
        });

        if (filtered.length === 0) {
            emptyState.classList.remove("hidden");
            bookmarksGrid.classList.add("hidden");
            return;
        }

        emptyState.classList.add("hidden");
        bookmarksGrid.classList.remove("hidden");

        filtered.forEach(b => {
            const card = document.createElement("div");
            card.className = `glass-panel bookmark-card status-${b.status}`;

            // Format publication/added date
            const dateObj = new Date(b.added_at);
            const dateStr = dateObj.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

            // Set state badges and text configurations
            let badgeHtml = "";
            let actionBtnHtml = "";
            let durationHtml = "";

            if (b.status === "completed") {
                badgeHtml = `<span class="badge badge-success">Listen Ready</span>`;
                actionBtnHtml = `
                    <button class="btn btn-card btn-card-play" data-id="${b.id}">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        <span>Listen Now</span>
                    </button>
                `;

                // Format estimated duration
                const durationMin = Math.round(b.audio_duration / 60);
                durationHtml = `
                    <div class="duration-text">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                        <span>${durationMin} min</span>
                    </div>
                `;
            } else if (["queued", "parsing", "synthesizing"].includes(b.status)) {
                let text = "Compiling";
                if (b.status === "parsing") text = "Parsing Content";
                if (b.status === "synthesizing") text = "Synthesizing Speech";

                badgeHtml = `<span class="badge badge-active">${text}</span>`;
                actionBtnHtml = `
                    <button class="btn-card" disabled>
                        <svg class="icon spin" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></svg>
                        <span>Processing...</span>
                    </button>
                `;
            } else {
                const label = b.status === "parsing_failed" ? "Parsing Failed" : (b.status === "failed" ? "Speech Failed" : "Unprocessed");
                const badgeClass = b.status.includes("failed") ? "badge-error" : "badge-pending";

                badgeHtml = `<span class="badge ${badgeClass}">${label}</span>`;
                actionBtnHtml = `
                    <button class="btn btn-card btn-generate" data-id="${b.id}">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        <span>Generate Audio</span>
                    </button>
                `;
            }

            card.innerHTML = `
                <div class="card-top">
                    <div class="card-meta">
                        <span class="card-domain">${b.domain}</span>
                        ${badgeHtml}
                    </div>
                    <h3 class="card-title">${escapeHTML(b.title)}</h3>
                    <p class="card-author">${b.author ? escapeHTML(b.author) : "No author snippet"}</p>
                </div>
                <div class="card-bottom-container" id="bottom-container-${b.id}">
                    <div class="card-footer">
                        <span class="duration-text">${dateStr}</span>
                        ${durationHtml}
                        ${actionBtnHtml}
                    </div>
                </div>
            `;

            bookmarksGrid.appendChild(card);
        });

        // Add Play Button event listeners
        document.querySelectorAll(".btn-card-play").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const id = e.currentTarget.getAttribute("data-id");
                expandAudioPlayer(id);
            });
        });

        // Add Generate Button event listeners
        document.querySelectorAll(".btn-generate").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const id = e.currentTarget.getAttribute("data-id");
                triggerGeneration(id);
            });
        });
    }

    function expandAudioPlayer(id) {
        const bookmark = bookmarks.find(b => b.id == id);
        if (!bookmark || !bookmark.audio_filename) return;

        const container = document.getElementById(`bottom-container-${id}`);
        if (!container) return;

        // Replace compile buttons with full playback controller
        container.innerHTML = `
            <div class="audio-player-inline">
                <audio controls autoplay src="/audio/${bookmark.audio_filename}"></audio>
                <div class="player-speeds" style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.4rem;">
                    <span style="font-size: 0.75rem; color: var(--text-dark); margin-right: auto; align-self: center;">Speed:</span>
                    <button class="btn-speed" data-speed="1">1x</button>
                    <button class="btn-speed" data-speed="1.25">1.25x</button>
                    <button class="btn-speed active" data-speed="1.5">1.5x</button>
                    <button class="btn-speed" data-speed="2">2x</button>
                </div>
            </div>
        `;

        const audio = container.querySelector("audio");
        audio.playbackRate = 1.5; // Default speed set to premium 1.5x standard reading speed

        // Handle speed selection buttons
        const speedButtons = container.querySelectorAll(".btn-speed");
        speedButtons.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const rate = parseFloat(e.currentTarget.getAttribute("data-speed"));
                audio.playbackRate = rate;
                speedButtons.forEach(b => b.classList.remove("active"));
                e.currentTarget.classList.add("active");
            });
        });
    }

    // ----------------- Smart Queue Auto-Polling -----------------

    function checkAndSetupPolling() {
        // Look for any active background jobs
        const hasActiveJobs = bookmarks.some(b =>
            ["queued", "parsing", "synthesizing"].includes(b.status)
        );

        if (hasActiveJobs) {
            if (!pollingInterval) {
                console.log("Active synthesis detected. Starting status auto-polling...");
                pollingInterval = setInterval(() => {
                    fetchBookmarks(true); // Poll silently in background
                }, 3000);
            }
        } else {
            if (pollingInterval) {
                console.log("No active synthesis jobs remaining. Stopping auto-polling.");
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
        }
    }

    // ----------------- Interactive Modals & Toast Banners -----------------

    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        let icon = "🔔";
        if (type === "success") icon = "✅";
        if (type === "error") icon = "❌";

        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
        toastContainer.appendChild(toast);

        // Slide out and remove toast after 4.5 seconds
        setTimeout(() => {
            toast.style.animation = "slideIn 0.3s reverse forwards";
            setTimeout(() => toast.remove(), 300);
        }, 4500);
    }

    function openRssModal() {
        const feedUrl = window.location.origin + "/rss.xml";
        rssUrlInput.value = feedUrl;
        modalRss.classList.remove("hidden");
    }

    function closeRssModal() {
        modalRss.classList.add("hidden");
    }

    function copyRssToClipboard() {
        rssUrlInput.select();
        rssUrlInput.setSelectionRange(0, 99999);
        navigator.clipboard.writeText(rssUrlInput.value)
            .then(() => showToast("📋 Podcast RSS feed copied to clipboard!", "success"))
            .catch(() => showToast("❌ Failed to copy to clipboard.", "error"));
    }

    // ----------------- Event Handlers -----------------

    btnSync.addEventListener("click", syncLibrary);
    btnRss.addEventListener("click", openRssModal);
    btnModalClose.addEventListener("click", closeRssModal);
    btnCopyRss.addEventListener("click", copyRssToClipboard);

    // Close modal when clicking dark backdrop
    modalRss.addEventListener("click", (e) => {
        if (e.target === modalRss) closeRssModal();
    });

    // Input Search Filtering
    searchInput.addEventListener("input", (e) => {
        searchQuery = e.target.value;
        renderBookmarks();
    });

    // Tab Button Selection
    tabBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            currentFilter = e.currentTarget.getAttribute("data-filter");
            renderBookmarks();
        });
    });

    // Stat Card Click Selection (Triggers filter jump)
    if (statPending) {
        statPending.addEventListener("click", () => {
            currentFilter = "pending";
            renderBookmarks();
        });
    }
    if (statActive) {
        statActive.addEventListener("click", () => {
            currentFilter = "active";
            renderBookmarks();
        });
    }
    if (statCompleted) {
        statCompleted.addEventListener("click", () => {
            currentFilter = "completed";
            renderBookmarks();
        });
    }

    // ----------------- Settings Modal -----------------

    const btnSettings = document.getElementById("btn-settings");
    const modalSettings = document.getElementById("modal-settings");
    const btnSettingsClose = document.getElementById("btn-settings-close");
    const settingEngine = document.getElementById("setting-engine");
    const settingVoice = document.getElementById("setting-voice");
    const settingReference = document.getElementById("setting-reference");
    const referenceFilename = document.getElementById("reference-filename");
    const btnSaveSettings = document.getElementById("btn-save-settings");

    // Track the currently selected file for upload
    let pendingReferenceFile = null;

    async function loadSettings() {
        try {
            const response = await fetch("/api/settings");
            if (!response.ok) return;
            const settings = await response.json();
            const ttsSettings = settings.tts || {};

            if (ttsSettings.tts_engine) {
                settingEngine.value = ttsSettings.tts_engine;
                await populateVoices(ttsSettings.tts_engine);
            }
            if (ttsSettings.tts_voice) {
                settingVoice.value = ttsSettings.tts_voice;
            }
        } catch (error) {
            console.error("Failed to load settings:", error);
        }
    }

    async function populateVoices(engine) {
        try {
            const response = await fetch(`/api/tts/voices/${engine}`);
            if (!response.ok) throw new Error("Failed to fetch voices");
            const data = await response.json();

            settingVoice.innerHTML = '<option value="">-- Select a voice --</option>';
            data.voices.forEach(voice => {
                const option = document.createElement("option");
                option.value = voice.id;
                option.textContent = voice.name;
                settingVoice.appendChild(option);
            });
        } catch (error) {
            console.error("Error loading voices:", error);
            if (engine === "edge") {
                settingVoice.innerHTML = `
                    <option value="">-- Select a voice --</option>
                    <option value="en-US-AvaNeural">Ava (US English - Recommended)</option>
                    <option value="en-US-GuyNeural">Guy (US English)</option>
                    <option value="en-US-JennyNeural">Jenny (US English)</option>
                    <option value="en-GB-RyanNeural">Ryan (UK English)</option>
                `;
            } else {
                settingVoice.innerHTML = '<option value="">-- No voices available --</option>';
            }
        }
    }

    btnSettings.addEventListener("click", () => {
        modalSettings.classList.remove("hidden");
        loadSettings();
    });

    btnSettingsClose.addEventListener("click", () => {
        modalSettings.classList.add("hidden");
    });

    modalSettings.addEventListener("click", (e) => {
        if (e.target === modalSettings) modalSettings.classList.add("hidden");
    });

    settingEngine.addEventListener("change", async () => {
        const engine = settingEngine.value;
        await populateVoices(engine);
        // Show/hide reference upload based on engine
        const groupRef = document.getElementById("group-reference");
        groupRef.style.display = engine === "pocket" ? "block" : "none";
    });

    settingReference.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
            pendingReferenceFile = file;
            referenceFilename.textContent = file.name;
        }
    });

    btnSaveSettings.addEventListener("click", async () => {
        const engine = settingEngine.value;
        const voice = settingVoice.value;

        if (!voice) {
            showToast("❌ Please select a voice.", "error");
            return;
        }

        btnSaveSettings.disabled = true;
        btnSaveSettings.textContent = "Saving...";

        try {
            // Save engine
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: new URLSearchParams({
                    key: "tts_engine",
                    value: engine,
                    section: "tts"
                })
            });

            // Save voice
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: new URLSearchParams({
                    key: "tts_voice",
                    value: voice,
                    section: "tts"
                })
            });

            // Upload reference audio if selected
            if (pendingReferenceFile && engine === "pocket") {
                const formData = new FormData();
                formData.append("file", pendingReferenceFile);
                const uploadResponse = await fetch("/api/tts/reference", {
                    method: "POST",
                    body: formData
                });
                if (!uploadResponse.ok) throw new Error("Reference upload failed");
                pendingReferenceFile = null;
                referenceFilename.textContent = "";
            }

            showToast("✅ Settings saved! They will take effect on the next synthesis.", "success");
            modalSettings.classList.add("hidden");
        } catch (error) {
            console.error("Save settings error:", error);
            showToast("❌ Failed to save settings.", "error");
        } finally {
            btnSaveSettings.disabled = false;
            btnSaveSettings.textContent = "Save Settings";
        }
    });

    // Initialize Application
    fetchBookmarks();
});

// Helper: Escape HTML strings to secure against XSS injections
function escapeHTML(str) {
    if (!str) return "";
    return str.replace(/[&<>'"]/g,
        tag => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "'": "&#39;",
            '"': "&quot;"
        }[tag] || tag)
    );
}
