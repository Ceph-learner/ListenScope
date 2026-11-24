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

免费、离线、本地运行的 Windows 桌面听歌分析、A/B 循环练习与扒谱辅助工具。本项目由作者与 AI 助手协作开发，旨在提供轻量、可控的本地音频分析工作台。

---

## 1. 界面预览

> **TODO**：UI 打磨分支（#42）合并后，此处将统一更新为最新实机与合成数据截图及演示 GIF。

---

## 2. 主要功能（已实测）

- **实时捕获与频谱**：通过 Windows 标准 WASAPI 进程环回（Build ≥ 20348）或系统环回捕获实时播放输出，提供波形、FFT / 对数频谱、基频 `F0` 与 `-50 ~ +50 cents` 音准刻度条。
- **和弦、调性与移调**：12-bin Chroma 热图、大/小三和弦与构成音识别、罗马级数、12 步和弦轨迹、纯 CPU Capo 移调联动及 24 调和弦练习弹窗（支持本地合成试听与 `.mid` 导出）。
- **120 秒回溯与 A/B 练习**：固定 120s 环形缓冲（`48 kHz / Stereo / float32`）、拖拽 A/B 选区、`0.5x–1.25x` 不变调变速回放（WSOLA）、12 个练习书签、Tap 定速节拍器及练习 WAV 导出。
- **本地 AI 分轨与混音（可选）**：独立子进程按需运行 2-Stem（MDX-Net）或 4-Stem（HTDemucs）分离，默认 6 秒安全分块与随时急停释放显存；支持 `0–24 dB` 贝斯独听增益与 FFT-YIN 贝斯最低音检测。
- **MIDI 导出与 Cubase 适配**：支持分轨后单轨转 MIDI 或直接打开本地单轨 WAV 转 MIDI，导出为 Steinberg Cubase 兼容 SMF Type-0（`480 TPB`）。
- **多主题与四语界面**：支持亮暗模式切换及多套内置配色，提供简体中文 / English / 한국어 / 日本語实时切换。

---

## 3. 系统要求

- **操作系统**：Windows 10 / 11（64 位，进程环回捕获需 Windows 11 / Windows 10 Build ≥ 20348）。
- **基准验证环境**：目前实机验证主要集中于 **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM**；其余显卡与系统配置尚未全面实测。
- **显卡需求**：**AI 分轨为可选功能**；实时频谱、和弦/调性/BPM 识别、A/B 慢放与节拍器仅需 CPU 即可运行。

---

## 4. 下载与安装

前往 [Releases](https://github.com/Ceph-learner/ListenScope/releases) 下载：

- **安装版**：`ListenScope-Setup-Windows-x64.exe`（默认安装至非 `C:` 盘或用户目录，卸载时保留 `exports\`）。
- **便携版**：`ListenScope-Core-Windows-x64-Portable.zip`（解压即用，`settings.json` 与导出文件保存在同级目录）。

**校验与 SmartScreen 提示**：
- 发行包尚未购买商业代码签名证书，Windows 首次运行时可能弹出 SmartScreen 提示，可点击「更多信息 → 仍要运行」。
- 建议下载后对照 Release 中的 `SHA256SUMS.txt` 校验文件完整性（PowerShell：`Get-FileHash <文件名> -Algorithm SHA256`）。
- 官方 Core 发行包**不内置 FFmpeg**；如需额外格式解码，FFmpeg 由用户自行安装或选用。

---

## 5. 快速上手

1. 运行 `ListenScope.exe`（无需显卡即可使用全部实时分析与 A/B 练习）。
2. 如需 AI 分轨或单轨转 MIDI，可在设置页 **`AI 与 MIDI 环境`** 一键扫描本机 PyTorch 或配置独立运行环境。
3. 在顶栏音源下拉框选择正在播放音乐的进程，点击开始捕获。

详细图文操作、典型扒谱场景与界面分区说明见 [用户指南 (docs/USER_GUIDE.md)](docs/USER_GUIDE.md)。

---

## 6. 在线更新说明

- 当前版本需从 GitHub Releases 页面手动下载新版安装包或便携包覆盖更新（便携版请保留 `settings.json`、`exports/` 及本地环境目录）。
- 应用内在线更新检查功能规划于后续版本（仅读取 GitHub 公开版本信息，不上传任何用户数据）。

---

## 7. 常见问题

- **没有 NVIDIA 显卡能用吗？** 可以，AI 分轨为可选功能，其余分析与练习功能仅使用 CPU。
- **捕获没有信号怎么办？** 请确认已选对正在出声的播放进程，或切换为系统环回测试。
- **如何彻底退出？** 若启用了最小化到托盘，请在系统托盘右键图标选择退出。

更多问题见 [常见问题 (docs/FAQ.md)](docs/FAQ.md) 与 [术语表 (docs/GLOSSARY.md)](docs/GLOSSARY.md)。

---

## 8. 已知限制

- 无边框主窗口暂不支持 Windows 11 Snap Layouts（悬停最大化按钮弹出贴靠布局菜单）。
- 除基准机（Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM）外的其他硬件配置尚未全面实测，遇到兼容问题欢迎附诊断包提交 Issue。

---

## 9. 参与贡献

欢迎提交 Issue 与 Pull Request！本项目遵循三环境隔离结构，Core 环境保持零 PyTorch / CUDA / TensorFlow 依赖：

```bash
# Linux / 无声卡环境测试
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

开发规范、基准测试、国际化与行为准则见 [贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md)、[行为准则 (CODE_OF_CONDUCT.md)](CODE_OF_CONDUCT.md)、[开发指南 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md)、[测试说明 (docs/TESTING.md)](docs/TESTING.md) 与 [路线图 (ROADMAP.md)](ROADMAP.md)。

---

## 10. 许可证、隐私与免责声明

- **开源协议**：本项目代码基于 [MIT License](LICENSE) 开源（`Copyright (c) 2026 Ceph-learner and ListenScope contributors`）。第三方组件清单与许可证文本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)；算法学术出处审计见 [docs/PROVENANCE.md](docs/PROVENANCE.md)。
- **模型权重**：仓库及官方发行包**不包含**任何 AI 模型权重文件；各模型（UVR / MDX-Net、HTDemucs、Basic Pitch）均遵循各自许可证与使用条款，用户在运行时下载前请自行核对。
- **免责声明**：
  - 本项目与腾讯、QQ 音乐及其他音乐平台无任何关联；
  - 本软件仅通过系统标准音频接口捕获本机正在播放的声音，不下载、不解密、不绕过任何 DRM 保护；
  - 用户应遵守所在地法律法规，对所处理音频的版权自行负责；
  - 本软件按「原样」提供，不作任何明示或暗示担保；如用于商业场景请自行评估相关算法与第三方组件条款。
- **商标声明**：文中提及的 QQ 音乐、Cubase、NVIDIA / RTX、Windows 等名称均为各自权利人的商标，本项目与其无关联。
- **隐私与 AI 协作文件**：软件全部功能本地运行，无遥测与数据上传（详见 [PRIVACY.md](PRIVACY.md)）。仓库内保留的 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`docs/HANDOFF.md`、`docs/AI_COLLABORATION.md` 与 `docs/review/` 用于记录项目约束与多轮协作上下文。

---

## 11. 致谢

感谢所有为音频信号处理、音源分离、MIDI 转录及桌面界面生态作出贡献的开源项目与研究者。完整致谢名单与出处链接见 [致谢与来源 (ACKNOWLEDGMENTS.md)](ACKNOWLEDGMENTS.md)。
