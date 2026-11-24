# Frequently Asked Questions (FAQ)

### 1. Can I use ListenScope without an NVIDIA GPU?
**Yes.** AI stem separation is optional. Live spectrum, pitch tracking, chord/key/BPM detection, 120s A/B time-stretch looping, metronome, and WAV export all run on CPU out of the box.

### 2. Why should I choose Per-Process Loopback capture?
Per-process loopback requires Windows 11 (Build ≥ 20348); Windows 10 users can use System Loopback. Per-process loopback captures audio only from the selected player or browser process. It prevents system notifications, voice chat, or game audio from polluting chord/pitch analysis and requires no virtual audio cable.

### 3. Why does Windows SmartScreen show a warning on first launch?
ListenScope binaries are not currently signed with a commercial code-signing certificate.
- Verify the file hash against `SHA256SUMS.txt` on the official GitHub Releases page (`Get-FileHash <filename> -Algorithm SHA256`).
- Once verified, click **More info → Run anyway**.

### 4. No signal or flat waveform after starting capture?
- Make sure the selected player process is actively playing unmuted audio. Some browsers/players spawn multiple processes—try another matching process in the dropdown, or switch temporarily to **System Loopback** to verify output.
- For headless/no-soundcard testing, run `python main.py --simulate`.

### 5. Low memory warning or AI separation refused?
ListenScope enforces three-tier RAM guardrails (5120 / 3072 / 2048 MiB) to protect 8 GB VRAM / 16 GB RAM systems from OOM crashes:
- Close memory-heavy browser tabs or background apps;
- Select a shorter A/B region before running AI separation;
- Click **E-STOP** (or press `Ctrl+Shift+E`) at any time to terminate the AI subprocess and release VRAM.

### 6. How do I quit ListenScope completely?
If minimize-to-tray is enabled in Settings, clicking the window close button hides ListenScope to the system tray. Right-click the **ListenScope tray icon** in the Windows taskbar notification area and select **Quit**.

### 7. How do I uninstall ListenScope, and where is my data stored?
- **Data location**: `settings.json`, `exports/`, `workspace_outputs/`, and `logs/` are stored in the **application directory** by default.
- **Installer edition**: Uninstall via Windows *Settings → Apps* or the uninstaller in the install folder. **`exports/` is preserved on uninstall** so your exported WAV/MIDI files are never lost.
- **Portable edition**: Simply delete the extracted folder (back up `exports/` first if needed).
