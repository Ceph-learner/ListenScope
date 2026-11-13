# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ListenScope Core Desktop Application (Windows).

Architecture (Section 21):
- Bundles ONLY Core GUI (PySide6 + pyqtgraph), WASAPI audio capture (proctap + pycaw + PyAudioWPatch),
  and CPU real-time DSP (numpy + scipy + librosa).
- Explicitly excludes heavy CUDA / PyTorch / ONNX Runtime / Demucs / Basic Pitch packages so the
  packaged Core folder stays lightweight (<1GB RAM) and launches instantly.
- AI separation runs out-of-process in the user's isolated `.venv-ai` interpreter configured via
  Settings -> `ai_python_executable` or `--ai-python`.
"""

from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "README.md"), "."),
        (str(project_root / "requirements-ai.txt"), "."),
        (str(project_root / "ai"), "ai"),
        (str(project_root / "separation"), "separation"),
    ],
    hiddenimports=[
        "proctap",
        "pycaw",
        "comtypes",
        "pyaudiowpatch",
        "pynvml",
        "sounddevice",
        "soundfile",
        "mido",
        "pyqtgraph",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchaudio",
        "torchvision",
        "triton",
        "onnxruntime",
        "audio_separator",
        "demucs",
        "basic_pitch",
        "tensorflow",
        "jax",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ListenScope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ListenScopeCore",
)
