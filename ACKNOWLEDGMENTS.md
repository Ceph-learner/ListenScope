# 致谢与来源

## 分轨与 MIDI

- **Nomad Karaoke 的 Audio Separator** 提供分轨模型的加载和推理接口。感谢 **Ultimate Vocal Remover** 的 Anjok07、aufr33 及社区对 UVR 模型生态的贡献，ListenScope 的 MDX 二轨路径使用其中的 `UVR-MDX-NET-Inst_HQ_3` 权重。 [Audio Separator](https://github.com/nomadkaraoke/python-audio-separator) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui)
- **Demucs / Hybrid Transformer Demucs** 提供本项目使用的 `htdemucs` 分轨后端与模型。感谢 Demucs 研究团队及维护者。 [Demucs](https://github.com/facebookresearch/demucs)
- **Minseok Kim、Woosung Choi 等研究者**公开发表了 KUIELab-MDX-Net 的分轨方法。感谢模型研究者以及训练和发布衍生权重的社区成员。 [KUIELab-MDX-Net 论文](https://arxiv.org/abs/2111.12203)
- **Spotify Basic Pitch** 提供单轨音频转 MIDI 的模型和工具，**Mido** 支持 MIDI 文件处理。 [Basic Pitch](https://github.com/spotify/basic-pitch) · [Mido](https://github.com/mido/mido)
- **PyTorch、ONNX Runtime、FFmpeg** 分别支撑模型推理与音频处理。 [PyTorch](https://pytorch.org/) · [ONNX Runtime](https://onnxruntime.ai/) · [FFmpeg](https://ffmpeg.org/)

## 捕获、分析与练习

- **Windows WASAPI 与 SMTC** 提供环回捕获和曲目信息接口。感谢 `proc-tap`、PyAudioWPatch、PyWinRT 以及 Python 音频工具维护者对 Windows 音频接入的贡献。 [WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/wasapi) · [SMTC 会话接口](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager) · [proc-tap](https://pypi.org/project/proc-tap/) · [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) · [PyWinRT](https://github.com/pywinrt/pywinrt)
- **NumPy、SciPy、librosa、SoundFile、python-sounddevice、Qt for Python 和 PyQtGraph** 支撑数值计算、音频分析、文件读写、播放和可视化。 [NumPy](https://numpy.org/) · [SciPy](https://scipy.org/) · [librosa](https://librosa.org/) · [SoundFile](https://github.com/bastibe/python-soundfile) · [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) · [Qt for Python](https://doc.qt.io/qtforpython-6/) · [PyQtGraph](https://www.pyqtgraph.org/)
- **Werner Verhelst 与 Marc Roelands** 提出的 WSOLA 算法，是本项目 A/B 回放不变调变速的技术基础。 [WSOLA 原始论文](https://doi.org/10.1109/ICASSP.1993.319366)
- **Carol L. Krumhansl 与 Mark Schmuckler** 的调性识别方法为本项目的实时调性推测提供了算法基础；调性轮廓同时参考 **David Temperley (1999)**、**Ibrahim Shaath (2011)** 与 **Joshua D. Albrecht & Daniel Shanahan (2013)** 的公开论文数值表。 [调性识别原文](https://academic.oup.com/book/40395/chapter-abstract/347203084)

## 体验参考

- 感谢 **PyQt-Fluent-Widgets** 提供 Qt 分组设置和滚动布局的公开示例，**Lucide** 为设置分类页图标提供灵感与许可参考（ISC / MIT）。 [Qt 设置示例](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/blob/master/examples/gallery/app/view/setting_interface.py) · [Lucide](https://github.com/lucide-icons/lucide)

## 模型权重与第三方许可说明

- 本仓库及官方发行包**不包含**任何 AI 模型权重文件；相关模型（如 `UVR-MDX-NET-Inst_HQ_3`、`htdemucs`、`Basic Pitch`）仅在用户按需配置环境后于本地运行时从上游下载。各模型权重均遵循其各自作者或发布方的许可证与使用条款（部分权重可能仅限非商业或研究用途），请用户在使用前自行核对并遵守对应条款。
- Core 发行包内第三方开源组件与许可证文本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)。
