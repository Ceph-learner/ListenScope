# ListenScope

<p align="left">
  <a href="README.md">简体中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20(x64)-0078D4?style=flat-square" alt="Windows" />
  <img src="https://img.shields.io/badge/Release-v1.0.0-00A878?style=flat-square" alt="Release" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
</p>

A **free, offline, local-first** Windows desktop workstation for real-time music analysis, A/B looping, AI stem separation, and transcription practice.

No encrypted cache downloads or virtual audio driver routing required. While listening in any desktop player or browser, ListenScope captures audio per process via standard Windows WASAPI APIs and provides real-time spectrum/pitch analysis, chord & key recognition, 120s ring-buffer looping, local AI stem separation, and Cubase-compatible MIDI export.

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope Live Analysis Demo (Simulated Signal)" width="820" />
</p>

---

## Quick Start (GUI One-Click Setup · No Terminal Needed)

1. **Download & Install**: Grab `ListenScope-Setup-Windows-x64.exe` or `ListenScope-Core-Windows-x64-Portable.zip` from [Releases](https://github.com/Ceph-learner/ListenScope/releases).
2. **Launch**: Double-click `ListenScope.exe`. **Real-time spectrum, chord/key/BPM detection, 120s A/B time-stretch looping, and metronome work out of the box** without a GPU.
3. **Configure AI & MIDI in GUI (Optional)**:
   - Open **`CONFIG // 设置`** (top-right) → **`AI & MIDI`**.
   - Click **Scan Local PyTorch** if PyTorch/Conda is already installed, or click **One-Click Setup AI + MIDI** to install isolated runtimes automatically and restart.
4. **Start Analyzing**: Select your player or browser in `AUDIO_IN` and click **`CAPTURE_START`**.

> Settings (`settings.json`), workspace cache, and exported WAV/MIDI files are stored **in the application directory** by default.

<p align="center">
  <img src="docs/images/settings_ai.png" alt="GUI One-Click AI & MIDI Setup" width="740" />
</p>

---

## Key Features

| Module | Overview |
| :--- | :--- |
| **Live Capture & Spectrum** | Per-process WASAPI loopback (Build ≥ 20348, no virtual cable) or system loopback using standard OS audio APIs (no DRM bypass or cache extraction); waveform, FFT / log-band spectrum, `F0` pitch & `-50 ~ +50 cents` tuning bar |
| **Chords, Key & Capo** | 12-bin Chroma heatmap, major/minor triads, Roman numerals, 12-step chord trail, CPU **Capo / transposition**, and 24-key practice dialog (with synth preview & `.mid` export) |
| **120s History & A/B Loop** | Fixed 120s ring buffer (`48 kHz / Stereo / float32`), drag-select A/B loop, `0.5x–1.25x` pitch-preserving WSOLA stretch, 12 bookmarks, Tap metronome & practice WAV export |
| **Local AI Stems & Mixer** | Isolated 2-Stem / 4-Stem separation with 6s safe chunking and instant E-STOP release; **`0–24 dB` Bass Solo Boost** and FFT-YIN bass pitch down to `B0`/`E1` |
| **MIDI & Cubase Export** | One-click stem-to-MIDI or standalone WAV-to-MIDI transcription; all exports normalized to **Steinberg Cubase-compatible SMF Type-0 (`480 TPB`)** |
| **Themes & Localization** | Defaults to **Acid Telemetry (Clinical Light)** with Light/Dark quick toggle; includes Classic, Arctic Slate, Graphite, Warm Sand, **ZH / EN / KO / JA** switching, and frameless rounded windows |

<p align="center">
  <img src="docs/images/chroma.png" alt="Chroma and Harmony View" width="440" />
  <img src="docs/images/main_dark.png" alt="Dark Mode View" width="440" />
</p>

---

## Hardware Compatibility

- Real-machine verification so far has focused on **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM**, with conservative 6s chunking and 5120 / 3072 / 2048 MiB RAM guardrails.
- Other GPU models, integrated graphics, and system configurations have not yet been broadly tested. If you encounter issues, please open an [Issue](https://github.com/Ceph-learner/ListenScope/issues) with your hardware details and diagnostic bundle.

---

## Development & Running from Source

ListenScope isolates dependencies across three Python environments (`core/`, `audio/`, `analysis/`, `ai/`, `separation/`, `streaming/`, `ui/`):

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe main.py
```

```bash
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen pytest -q --tb=short
```

---

## Documentation & License

- [Architecture (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) · [Decisions (docs/DECISIONS.md)](docs/DECISIONS.md) · [Development (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md) · [Packaging (docs/PACKAGING.md)](docs/PACKAGING.md) · [Contributing (CONTRIBUTING.md)](CONTRIBUTING.md)
- Licensed under the [MIT License](LICENSE). See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for third-party credits.
- ListenScope is not affiliated with any third-party music player, DAW, or hardware vendor.
