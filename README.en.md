# ListenScope

<p align="left">
  <a href="README.md">简体中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20(x64)-0078D4?style=flat-square" alt="Windows" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
  <a href="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml"><img src="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml/badge.svg" alt="Tests" /></a>
</p>

A **free, offline, local-first** Windows desktop workstation for real-time audio analysis, A/B looping, AI stem separation, and transcription practice. Developed collaboratively by the author and AI assistants with a focus on lightweight, controllable local processing.

---

## 1. Screenshots

![Realtime Spectrum & Waveform (Dark Theme)](docs/images/listenscope_dark_en_spectrum_1366x768.png)

| Light Theme | Chords, Key & Tempo | Stem Mixer & MIDI |
| :---: | :---: | :---: |
| ![Light Theme](docs/images/listenscope_light_spectrum_1366x768.png) | ![Chords & Key](docs/images/listenscope_light_chord_1366x768.png) | ![Stem Mixer](docs/images/listenscope_light_mixer_empty_1366x768.png) |

> All screenshots above are generated offscreen from deterministic synthetic audio via `scripts/make_screenshots.py` (no real track titles or personal paths).

---

## 2. Key Features (Tested)

- **Live Capture & Spectrum**: Captures live playback per process via standard Windows WASAPI loopback (Build ≥ 20348) or system loopback; provides waveform, FFT / log-band spectrum, `F0` pitch tracking, and `-50 ~ +50 cents` tuning bar.
- **Chords, Key & Transposition**: 12-bin Chroma heatmap, major/minor triad recognition, Roman numerals, 12-step chord trail, CPU Capo transposition, and a 24-key chord practice dialog (with synth preview and `.mid` export).
- **120s History & A/B Loop**: Fixed 120s ring buffer (`48 kHz / Stereo / float32`), drag-select A/B loop, `0.5x–1.25x` pitch-preserving WSOLA time-stretching, 12 bookmarks, Tap metronome, and practice WAV export.
- **Local AI Stems & Mixer (Optional)**: Runs 2-Stem (MDX-Net) or 4-Stem (HTDemucs) separation in an isolated subprocess with conservative 6s chunking and instant E-STOP memory release; includes `0–24 dB` Bass Solo Boost and FFT-YIN bass pitch detection.
- **MIDI & Cubase Export**: One-click stem-to-MIDI or standalone WAV-to-MIDI transcription normalized to Steinberg Cubase-compatible SMF Type-0 (`480 TPB`).
- **Themes & Localization**: Light/Dark toggle, multiple built-in palettes, and live switching between Simplified Chinese, English, Korean, and Japanese.

---

## 3. System Requirements

- **OS**: Windows 10 / 11 (64-bit; per-process loopback requires Windows 11 or Windows 10 Build ≥ 20348).
- **Verified Baseline Hardware**: Real-machine testing has focused on **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM**. Other GPUs and system configurations have not yet been broadly tested.
- **GPU**: **AI stem separation is optional**; live spectrum, chord/key/BPM analysis, A/B looping, and metronome run on CPU only.

---

## 4. Download & Installation

Download from [Releases](https://github.com/Ceph-learner/ListenScope/releases):

- **Installer**: `ListenScope-Setup-Windows-x64.exe` (preserves `exports\` on uninstall).
- **Portable**: `ListenScope-Core-Windows-x64-Portable.zip` (extract and run; `settings.json` and exports are stored in the application directory).

**Verification & SmartScreen Notice**:
- Binaries are not currently signed with a commercial code-signing certificate, so Windows SmartScreen may show a warning on first launch ("More info → Run anyway").
- Verify your download against `SHA256SUMS.txt` in the release (PowerShell: `Get-FileHash <filename> -Algorithm SHA256`).
- **FFmpeg is not bundled** in the official Core release; users may install or provide FFmpeg separately if needed.

---

## 5. Quick Start

1. Launch `ListenScope.exe` (real-time analysis and A/B looping work out of the box without a GPU).
2. *(Optional)* To use AI separation or WAV-to-MIDI, open Settings → **`AI & MIDI`** to scan a local PyTorch environment or configure isolated runtimes.
3. Select your active audio player process in the top bar and click Start Capture.

For detailed walkthroughs, transcription workflows, and UI layout explanations, see [User Guide (docs/USER_GUIDE.en.md)](docs/USER_GUIDE.en.md).

---

## 6. Updates

- Updates are currently installed manually by downloading a newer installer or portable archive from GitHub Releases (when updating the portable edition, preserve `settings.json`, `exports/`, and local runtime folders).
- In-app update checking is planned for a future release (reading only public release metadata without uploading user data).

---

## 7. FAQ

- **Can I use ListenScope without an NVIDIA GPU?** Yes. AI separation is optional; all real-time analysis and A/B practice features run on CPU.
- **No signal when capturing?** Verify that the target player process is actively outputting audio, or test with system loopback.
- **How do I quit completely?** If minimize-to-tray is enabled, right-click the system tray icon and choose Quit.

See [FAQ (docs/FAQ.en.md)](docs/FAQ.en.md) and [Glossary (docs/GLOSSARY.en.md)](docs/GLOSSARY.en.md) for more.

---

## 8. Known Limitations

- The frameless main window does not yet support Windows 11 Snap Layouts on hover over the maximize button.
- Hardware configurations outside the baseline machine (Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM) have not been comprehensively tested.

---

## 9. Contributing

Issues and Pull Requests are welcome! ListenScope isolates dependencies across three environments, keeping Core free of PyTorch / CUDA / TensorFlow:

```bash
# Linux / headless offscreen tests
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/TESTING.md](docs/TESTING.md), and [ROADMAP.md](ROADMAP.md).

---

## 10. License, Privacy & Disclaimers

- **License**: MIT License ([LICENSE](LICENSE), `Copyright (c) 2026 Ceph-learner and ListenScope contributors`). Third-party component notices and license texts are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [licenses/](licenses/). Algorithm provenance is documented in [docs/PROVENANCE.md](docs/PROVENANCE.md).
- **Model Weights**: Neither the repository nor official releases bundle AI model weights. Models (UVR / MDX-Net, HTDemucs, Basic Pitch) are downloaded from upstream sources at runtime under their own licenses and terms; users must review those terms before use.
- **Disclaimers**:
  - This project is not affiliated with Tencent, QQ Music, or any music streaming platform.
  - ListenScope only captures audio currently playing on your machine via standard OS audio APIs; it does not download, decrypt, or bypass any DRM.
  - Users are solely responsible for complying with local laws and copyright terms for any audio they process.
  - The software is provided "AS IS" without warranty of any kind; if used in commercial contexts, please perform your own legal/license evaluation.
- **Trademarks**: Names such as QQ Music, Cubase, NVIDIA / RTX, and Windows belong to their respective owners; ListenScope has no affiliation with them.
- **Privacy & AI Collaboration Files**: ListenScope runs locally with zero telemetry ([PRIVACY.md](PRIVACY.md)). Files such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/HANDOFF.md`, `docs/AI_COLLABORATION.md`, and `docs/review/` are retained to document project constraints and multi-session development context.

---

## 11. Acknowledgments

We thank the open-source projects and researchers whose work underpins audio DSP, source separation, MIDI transcription, and desktop UI tooling. Full credits and links are preserved in [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
