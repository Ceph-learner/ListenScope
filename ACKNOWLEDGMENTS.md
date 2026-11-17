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
- **Carol L. Krumhansl 与 Mark Schmuckler** 的调性识别方法为本项目的实时调性推测提供了算法基础。 [调性识别原文](https://academic.oup.com/book/40395/chapter-abstract/347203084)

## 体验参考

- 感谢 **PyQt-Fluent-Widgets** 提供 Qt 分组设置和滚动布局的公开示例，**Lucide** 为设置原型和原生分类页提供导航图标。许可随原型和应用分发。 [Qt 设置示例](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/blob/master/examples/gallery/app/view/setting_interface.py) · [Lucide](https://github.com/lucide-icons/lucide)

- 感谢 **LioRael 与 Lenso UI 贡献者**。ListenScope 的 Lenso 预设借鉴了面板材质与小面积光学层分工。参考提交 `81b06bf` 中的调度、偏好和效果回收实现，使用 Qt 原生样式独立实现。Codex 和 Claude Code 预设借鉴各自的桌面与终端视觉风格。 [Lenso UI 源码](https://github.com/LioRael/lenso-ui/tree/81b06bf475d02c6fefd373ef04d0b942e46d82f2/packages/glass/src) · [Codex](https://openai.com/index/introducing-the-codex-app/) · [Claude Code](https://code.claude.com/docs/en/interactive-mode)

- **Moises Live** 的边听边调节分轨音量，为本项目的实验性近实时分轨体验提供了参考。 [Moises Live 官方介绍](https://moises.ai/newsroom/company-milestones/namm-2025/)
