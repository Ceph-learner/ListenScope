# Privacy Policy

**ListenScope** is designed as a **local-first, offline** desktop application.

## Data Collection & Telemetry
- ListenScope **does not collect, store, or transmit** any telemetry, analytics, crash reports, usage statistics, or audio recordings to any external server.
- All audio capture, DSP analysis, AI stem separation, and MIDI transcription run locally on your machine.
- Settings (`settings.json`), logs, workspace caches, and exported WAV/MIDI files remain strictly on your local disk.

## Network Requests
- **AI / MIDI Runtime Setup (User-Initiated Only)**: When you explicitly trigger AI/MIDI environment setup or model download in Settings, `pip` or the separation/transcription libraries download packages and model weights from their upstream registries (PyPI / Hugging Face / GitHub).
- **Update Checks (Planned Feature)**: When in-app update checking is enabled in a future release, ListenScope will only send a read-only HTTPS GET request to public GitHub Releases metadata (`api.github.com`) and will not upload any device, user, or usage data.
