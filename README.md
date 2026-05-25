# VibeListen

> Turn your reading list into a personal podcast.

## 🎯 Goal

**VibeListen** is a modern, highly responsive web application that lets users catch up on their growing backlog of read-it-later articles via a generated audio podcast feed. The project aims to showcase elegant UI/UX design patterns (glassmorphism, vibrant gradients, smooth micro‑animations) while providing a solid foundation for future feature expansion. This is my first exploration into the world of Vibe Coding. 

## 🚀 Current State

-  **Frontend**: Vanilla HTML/CSS/JS with responsive layout.
- **Backend**: Flask API serving RSS feeds.
- **Sync**: Raindrop.io integration (test token).
- **Audio Engine**: Edge TTS for on‑the‑fly audio generation.
- **CI/CD**: GitHub Actions linting & testing.

## 🗺️ Roadmap (Future Phases)

| Phase | Milestones | Estimated Completion |
|-------|------------|----------------------|
| **Phase 1 – Foundation and Simple Cloud MVP** | Setup basic project layout, Raindrop.io sync with personal Test Token, Edge TTS for audio generation, Dynamically generated RSS. | Complete |
| **Phase 2 – Local AI TTS Integration** | Plugable TTS Adapter system, PiperTTS and Pocket TTS integration, Background Process Queue for audio generation. | TBD |
| **Phase 3 – Additional Read-it-Later Providers** | Pluggable read-it-later integration, Instapaper and Pocket integration. | TBD |
| **Phase 4 – Optimization, Multi-Platform and Packaging** | Dockerfile creation, Setup simple scripts for tailscale or ngrok setup, Optimization. | TBD |
| **Phase 5 - Premium UI Web Dashboard** | Improve the Web UI, add responsive layouts for desktop and mobile, interactive local player, and settings management forms. | TBD |
---

*Feel free to explore the repository, raise issues, or contribute via pull requests. Together we’ll make VibeListen the go‑to destination for music lovers.*

## 🔧 Installation
```bash
git clone https://github.com/sean-m-baker/VibeListen.git
cd VibeListen
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Set environment variables
export RAINDROP_TOKEN=your_token
python run.py