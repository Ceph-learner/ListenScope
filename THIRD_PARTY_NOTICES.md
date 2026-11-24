# Third-Party Notices

ListenScope is licensed under the **MIT License** (see [LICENSE](LICENSE)).  
This document lists the third-party software, libraries, icons, and optional components used or bundled by **ListenScope Core**, generated from `pip-licenses` in the Linux Core environment with Windows-only dependencies supplemented from PyPI metadata (`待 Windows 构建核对`).

---

## 1. LGPL & Weak-Copyleft Notices (Dynamic Linking / Replaceability)

### Qt for Python (`PySide6`, `PySide6_Addons`, `PySide6_Essentials`, `shiboken6`)
- **License**: `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` (used by ListenScope under **LGPL-3.0-only**)
- **License Text**: [licenses/LGPL-3.0.txt](licenses/LGPL-3.0.txt)
- **URL**: <https://pyside.org>
- **User Rights**: Under the GNU Lesser General Public License v3.0, you are free to replace the dynamically linked Qt / PySide6 shared libraries (`.dll` / `.pyd` / `.so`) in the ListenScope distribution with your own compatible build (e.g., inside `_internal\PySide6\` in the frozen Core package).

### `soxr` (`python-soxr` / `libsoxr`)
- **License**: `LGPL-2.1-or-later`
- **License Text**: [licenses/LGPL-2.1.txt](licenses/LGPL-2.1.txt)
- **URL**: <https://github.com/dofuuz/python-soxr>
- **Note**: Transitive dependency of `librosa`; dynamically linked as a Python extension module.

### `certifi`
- **License**: `MPL-2.0` (Mozilla Public License 2.0)
- **URL**: <https://github.com/certifi/python-certifi>
- **Note**: Transitive dependency of `requests` / `pooch`.

---

## 2. Core Python Packages (Linux Core Environment · `pip-licenses`)

| Package | Version | License | Project URL |
|---|---|---|---|
| PySide6 | 6.9.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://pyside.org> |
| PySide6_Addons | 6.9.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://pyside.org> |
| PySide6_Essentials | 6.9.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://pyside.org> |
| shiboken6 | 6.9.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://pyside.org> |
| pyqtgraph | 0.14.0 | MIT | <http://www.pyqtgraph.org> |
| numpy | 2.5.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | <https://numpy.org> |
| scipy | 1.18.1 | BSD-3-Clause (wheels may include LGPL-2.1-or-later `libquadmath` on Linux) | <https://scipy.org/> |
| librosa | 1.0.1 | ISC | <https://librosa.org> |
| soundfile | 0.14.0 | BSD-3-Clause (bundles libsndfile, LGPL-2.1) | <https://github.com/bastibe/python-soundfile> |
| sounddevice | 0.5.6 | MIT (bundles PortAudio, MIT) | <https://github.com/spatialaudio/python-sounddevice/> |
| mido | 1.3.3 | MIT | <https://github.com/mido/mido> |
| psutil | 7.2.2 | BSD-3-Clause | <https://github.com/giampaolo/psutil> |
| nvidia-ml-py | 13.615.71 | BSD-3-Clause | <https://forums.developer.nvidia.com> |
| numba | 0.68.1 | BSD-2-Clause | <https://numba.pydata.org> |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | <http://llvmlite.readthedocs.io> |
| scikit-learn | 1.9.1 | BSD-3-Clause | <https://scikit-learn.org> |
| joblib | 1.6.0 | BSD-3-Clause | <https://joblib.readthedocs.io> |
| threadpoolctl | 3.8.0 | BSD-3-Clause | <https://github.com/joblib/threadpoolctl> |
| soxr | 1.1.0 | LGPL-2.1-or-later | <https://github.com/dofuuz/python-soxr> |
| pooch | 1.9.0 | BSD-3-Clause | <https://github.com/fatiando/pooch> |
| requests | 2.34.2 | Apache-2.0 | <https://github.com/psf/requests> |
| urllib3 | 2.8.0 | MIT | <https://github.com/urllib3/urllib3> |
| charset-normalizer | 3.5.3 | MIT | <https://github.com/jawah/charset_normalizer> |
| idna | 3.20 | BSD-3-Clause | <https://github.com/kjd/idna> |
| certifi | 2026.10.23 | MPL-2.0 | <https://github.com/certifi/python-certifi> |
| cffi | 2.1.1 | MIT-0 | <https://github.com/python-cffi/cffi> |
| pycparser | 3.12 | BSD-3-Clause | <https://github.com/eliben/pycparser> |
| decorator | 5.3.2 | BSD-2-Clause | <https://github.com/micheles/decorator> |
| lazy-loader | 0.6 | BSD-3-Clause | <https://scientific-python.org/specs/spec-0001/> |
| packaging | 26.4 | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> |
| platformdirs | 4.14.8 | MIT | <https://github.com/tox-dev/platformdirs> |
| msgpack | 1.2.4 | Apache-2.0 | <https://msgpack.org/> |
| audioread / cloudpickle | 3.1.3 | BSD-3-Clause | <https://github.com/cloudpipe/cloudpickle> |
| typing_extensions | 4.16.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |

---

## 3. Windows-Only Core Packages (`待 Windows 构建核对` · From PyPI Metadata)

> Note: These packages are only installed on Windows (`requirements-windows.txt`) and cannot be inspected by `pip-licenses` in Linux. Versions and licenses below were retrieved from PyPI metadata and must be verified against the frozen Windows `dist/ListenScopeCore/` artifact on a Windows build (`待 Windows 构建核对`).

| Package | PyPI Latest Version | License | Project URL | Status |
|---|---|---|---|---|
| proc-tap | 1.1.1 | MIT | <https://github.com/m96-chan/ProcTap> | 待 Windows 构建核对 |
| pycaw | 20260927 | MIT | <https://github.com/AndreMiras/pycaw> | 待 Windows 构建核对 |
| comtypes | 1.5.0 | MIT | <https://github.com/enthought/comtypes> | 待 Windows 构建核对 |
| PyAudioWPatch | 0.2.12.9 | Apache-2.0 | <https://github.com/s0d3s/PyAudioWPatch/> | 待 Windows 构建核对 |
| winrt-runtime | 4.2.1 | MIT | <https://github.com/pywinrt/pywinrt> | 待 Windows 构建核对 |
| winrt-Windows.Foundation | 4!10.0.28000.2957 | MIT | <https://github.com/pywinrt/pywinrt> | 待 Windows 构建核对 |
| winrt-Windows.Foundation.Collections | 4!10.0.28000.2957 | MIT | <https://github.com/pywinrt/pywinrt> | 待 Windows 构建核对 |
| winrt-Windows.Media.Control | 4!10.0.28000.2957 | MIT | <https://github.com/pywinrt/pywinrt> | 待 Windows 构建核对 |

---

## 4. Icons, Colormaps & Optional External Tools

- **Lucide Icons (`lucide-static` v1.78.0)** (`ui/assets/settings/` and `ui/assets/icons/`, registered in `ui/assets/icons/ICONS.md`): Licensed under the **ISC License** (with Feather-derived icons under **MIT License**). Full license text: [licenses/ISC-Lucide.txt](licenses/ISC-Lucide.txt) and [ui/assets/settings/LICENSE.txt](ui/assets/settings/LICENSE.txt).
- **Spectrogram Colormaps**: Dark-theme `inferno` colormap via PyQtGraph (derived from Matplotlib's `inferno` by Nathaniel J. Smith, Stefan van der Walt, and Eric Firing, **CC0 1.0** public domain). Light-theme colormap is generated locally in OKLab space (`ui/acid_style.py:_oklab_light_colormap_lut`) with monotonically decreasing lightness.
- **FFmpeg (Optional External Tool)**: The official Core release ZIP and installer do **not** bundle FFmpeg. Users who wish to decode additional formats (e.g., MP3/FLAC/M4A via external tools) may install FFmpeg separately; any FFmpeg binary placed in `tools/ffmpeg/` is governed by its own build license (LGPL or GPL depending on the distribution).
- **AI / MIDI Optional Runtimes**: PyTorch, ONNX Runtime, `audio-separator`, `demucs`, and `basic-pitch` are **not** bundled in the Core release; they are installed into isolated user environments on demand and remain subject to their respective upstream licenses and model weight terms.
