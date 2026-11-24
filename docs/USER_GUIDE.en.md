# ListenScope User Guide (5-Minute Quick Start)

> **Screenshots (TODO)**: Annotated UI screenshots will be added here after the UI polish branch (#42) is merged.

## 1. 5-Minute Quick Start

1. **Launch**: Double-click `ListenScope.exe`. **Live spectrum, pitch, chord/key/BPM detection, 120s A/B time-stretch looping, and metronome work out of the box without a GPU.**
2. **Select Audio Source & Capture**:
   - Choose your active player or browser process in the top-bar source selector (or switch to System Loopback to capture all system audio).
   - Click Start Capture to view live waveforms, spectrum, and harmonic analysis.
3. **(Optional) Configure AI Stems & MIDI**:
   - Click the Settings icon (top-right) → **AI & MIDI**.
   - Click **Scan Local PyTorch** if you already have PyTorch/Conda installed, or click **One-Click Setup AI + MIDI** and restart once installation completes.

---

## 2. UI Areas Overview

| Area | Purpose |
|---|---|
| **Top Bar** | Audio source selector, Capture Start/Stop, Light/Dark theme toggle, Settings, and an always-visible **E-STOP** button on the right (turns red during AI jobs; press or hit `Ctrl+Shift+E` to abort and release VRAM). |
| **Main Tabs** | Spectrum/Pitch, Chords/Key, Stem Mixer, and Waveform/Timeline views. |
| **Bottom Dock (A/B Loop & Metronome)** | Displays the 120s rolling audio buffer; drag to set A/B loop markers, adjust `0.5x–1.25x` pitch-preserving playback speed, manage 12 bookmarks, use Tap metronome, and export practice WAVs. |
| **Status Footer** | Shows version, active audio source & sample rate, analysis latency (`p50`), buffer duration, CPU usage, and reduced-motion toggle. |

---

## 3. Four Common Workflows

### 1. Transcribing Bass Lines
1. Capture a section of a song, select the target phrase on the timeline, and run **AI 2-Stem** or **4-Stem** separation.
2. Open the **Mixer** tab, solo the **Bass** stem, and raise the **`0–24 dB` Bass Solo Boost** if needed.
3. Read the FFT-YIN lowest-pitch readout (down to `B0` / `E1`) while looping at `0.75x` speed.

### 2. Finding Key & Chord Progressions
1. Open the **Chords/Key** tab and play 10–15 seconds of a verse or chorus.
2. Inspect the 12-bin Chroma heatmap, recognized triads, Roman numerals, 12-step chord trail, and estimated key/BPM.
3. Adjust the **Capo** offset to view transposed chord degrees, or open the **24-Key Chord Practice** dialog to audition and export `.mid`.

### 3. Slow-Down A/B Loop Practice
1. Drag across the 120s buffer to mark your A/B loop (or use the `10s / 30s / 60s` quick presets).
2. Lower playback speed (`0.5x–0.9x`) using pitch-preserving WSOLA time-stretching.
3. Save up to 12 bookmarks and enable the metronome with count-in for practice.

### 4. Exporting MIDI to Cubase
1. After AI separation, click **To MIDI** on any stem, or use **Open Solo WAV to MIDI** for an existing local mono/solo track.
2. All chord, beat/drum, and solo MIDI exports are normalized to **Steinberg Cubase-compatible SMF Type-0 (`480 TPB`)**.
3. Drag the exported `.mid` file from `exports/` directly into your Cubase project.
