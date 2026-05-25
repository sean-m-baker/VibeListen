# VibeListen


## 🎯 Goal

**VibeListen** is a modern, highly responsive web application that lets users catch up on their growing backlog of read-it-later articles via a generated audio podcast feed. The project aims to showcase elegant UI/UX design patterns (glassmorphism, vibrant gradients, smooth micro‑animations) while providing a solid foundation for future feature expansion. This is my first exploration into the world of Vibe Coding. 

## 🚀 Current State

- **Frontend**: Implemented with vanilla HTML, CSS, and JavaScript using a component‑based architecture. The home page features:
  - Dark glass‑style navigation bar.
  - Hero section with animated music‑wave visualisation.
  - Responsive layout for desktop and mobile.
- **Backend**: Basic API scaffold (Python/Flask) serving static content and placeholder endpoints for future music‑data integration.
- **Testing**: Initial unit tests for core UI components and API health checks.
- **CI/CD**: GitHub Actions pipeline set up for linting, testing, and automatic deployment to the staging environment.

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
