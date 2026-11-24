<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/design/icon/listenscope_master_dark.svg" />
  <img src="docs/design/icon/listenscope_master_light.svg" alt="ListenScope" width="112" />
</picture>

# ListenScope

**听歌的时候，顺手把它扒下来。**

一个免费、离线、在你自己电脑上运行的 Windows 练耳与扒谱小工作台

简体中文 · [English](README.en.md) · [한국어](README.ko.md) · [日本語](README.ja.md)

<a href="https://github.com/Ceph-learner/ListenScope/releases"><img src="https://img.shields.io/github/v/release/Ceph-learner/ListenScope?style=flat-square&color=00A878&label=下载" alt="Release" /></a>
<img src="https://img.shields.io/badge/Windows-10%20%2F%2011%20x64-0078D4?style=flat-square" alt="Windows" />
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="MIT" /></a>
<a href="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml"><img src="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests" /></a>

</div>

<br />

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope 实时分析演示（合成信号）" width="860" />
</p>

扒歌的时候，你是不是也经常这样：一句 solo 来回拖进度条十几遍、调性听了半天拿不准、贝斯埋在混音里怎么也听不清？

ListenScope 想把这些麻烦事揽过来。你照常在播放器或浏览器里放歌，它在旁边安静地「听」，把**音高、和弦、调性、速度**实时画给你看；刚才那句没听清？**往回翻 120 秒，框选、放慢、循环**，直到你弹对为止。需要的话，还能用本地 AI 把人声、鼓、贝斯**拆开单独听**，再导出 MIDI 丢进 DAW 里接着改。

不用装虚拟声卡，不用下载什么缓存文件，所有处理都在你自己的电脑上完成。

---

## ✨ 它能帮你做什么

<table>
<tr>
<td width="50%" valign="top">

### 🎧 边听边看
从指定播放器进程（或整台电脑）实时捕获声音，显示波形、频谱、基频与 ±50 音分的音准尺。

</td>
<td width="50%" valign="top">

### 🎼 和弦与调性
Chroma 热图、和弦与构成音、罗马级数、和弦轨迹，加上 Capo 移调联动和 24 调和弦练习窗。

</td>
</tr>
<tr>
<td valign="top">

### 🔁 回放 · 慢放 · 循环
始终保留最近 120 秒。拖一下就是 A/B 循环，0.5×–1.25× 变速不变调，还有书签、节拍器和练习录音导出。

</td>
<td valign="top">

### 🪄 AI 分轨（可选）
本地运行 2 轨（人声 / 伴奏）或 4 轨（人声 / 鼓 / 贝斯 / 其他）分离，贝斯可单独放大 0–24 dB 来听。

</td>
</tr>
<tr>
<td valign="top">

### 🎹 导出 MIDI
分轨后的单轨，或者你自己的 WAV，都能转成 MIDI；格式按 Cubase 兼容的 SMF Type-0 整理好。

</td>
<td valign="top">

### 🌗 看着舒服
亮色 / 暗色一键切换，多套配色可选；界面支持简体中文、English、한국어、日本語。

</td>
</tr>
</table>

> 实时分析、A/B 练习和节拍器只用 CPU，**没有独立显卡也能用**。AI 分轨和 MIDI 转写是可选功能。

---

## 🖼️ 界面一览

<p align="center">
  <img src="docs/images/listenscope_light_spectrum_1366x768.png" alt="实时频谱与波形（浅色）" width="860" />
</p>

<table>
<tr>
<td align="center" width="33%"><img src="docs/images/listenscope_dark_en_spectrum_1366x768.png" alt="深色主题" /><br /><sub>深色主题</sub></td>
<td align="center" width="33%"><img src="docs/images/listenscope_light_chord_1366x768.png" alt="和弦与调性" /><br /><sub>和弦 · 调性 · 节拍</sub></td>
<td align="center" width="33%"><img src="docs/images/listenscope_light_mixer_empty_1366x768.png" alt="分轨混音" /><br /><sub>分轨混音与 MIDI</sub></td>
</tr>
</table>

<p align="center"><sub>截图与演示均使用合成信号生成，不含任何真实歌曲。</sub></p>

---

## 🚀 三步开始

1. **下载** —— 到 [Releases](https://github.com/Ceph-learner/ListenScope/releases) 选一个：
   - 安装版 `ListenScope-Setup-Windows-x64.exe`
   - 便携版 `ListenScope-Core-Windows-x64-Portable.zip`（解压即用，设置和导出文件都放在软件旁边，不往 C 盘乱塞东西）
2. **打开** —— 运行 `ListenScope.exe`，在顶部音源里选中正在放歌的播放器，点「开始捕获」。
3. **想用 AI 分轨？** —— 打开 设置 → **AI 与 MIDI 环境**：已经装过 PyTorch 的点「扫描」，没装过的点「一键配置」，等它跑完重启一下就好。

<p align="center">
  <img src="docs/images/settings_ai.png" alt="设置页一键配置 AI 与 MIDI" width="720" />
</p>

更详细的图文说明和几个典型扒谱场景，写在 [用户指南](docs/USER_GUIDE.md) 里。

<details>
<summary><b>第一次运行弹出蓝色的 SmartScreen 提示？</b></summary>

<br />

这是因为发行包还没有购买代码签名证书，并不代表有问题。点「更多信息 → 仍要运行」即可。

如果不放心，可以对照 Release 里的 `SHA256SUMS.txt` 校验一下：

```powershell
Get-FileHash .\ListenScope-Setup-Windows-x64.exe -Algorithm SHA256
```

</details>

---

## 💻 运行环境

| | 说明 |
| :--- | :--- |
| 系统 | Windows 10 / 11（64 位） |
| 按进程捕获 | 需要 **Windows 11**；Windows 10 可以使用「系统环回」捕获整机声音 |
| 显卡 | 可选，只在 AI 分轨时使用（NVIDIA 显卡体验最好） |
| 实测环境 | Windows 11 · RTX 5060 Ti 8 GB · 16 GB 内存 |

说实话，目前主要只在上面这一台电脑上认真测过。如果你的配置跑起来有问题，非常欢迎[开个 Issue](https://github.com/Ceph-learner/ListenScope/issues/new/choose) 告诉我，最好附上诊断包和你的硬件信息。

**已知的小遗憾**：无边框窗口暂时不支持 Windows 11 的贴靠布局（鼠标悬停最大化按钮弹出的那个菜单），已经记在计划里了。

---

## ❓ 常见问题

- **没有 NVIDIA 显卡能用吗？** 能。除了 AI 分轨，其他功能都只用 CPU。
- **捕获不到声音？** 先确认选中的是正在出声的那个程序；不行就切到「系统环回」试试。
- **点了关闭，程序还在？** 可能是最小化到托盘了，右键托盘图标选「退出」就好。
- **怎么更新？** 目前请到 Releases 下载新版覆盖。便携版记得保留 `settings.json` 和 `exports\` 文件夹。

更多问题见 [FAQ](docs/FAQ.md)，名词看不懂可以查 [术语表](docs/GLOSSARY.md)。

---

## 🌱 关于这个项目

我不是专业开发者，ListenScope 是我在多个 AI 助手的帮助下，一点一点做出来、再在自己电脑上反复实测打磨的。所以它一定还有不少粗糙的地方，也难免有我没想到的问题。

如果它能帮你少拖几次进度条、多听清一个和弦，我就很开心了。也欢迎任何形式的反馈：一个 Issue、一句建议，或者一个 ⭐，对我来说都是很大的鼓励。

<details>
<summary><b>想从源码运行或参与开发？</b></summary>

<br />

项目分成三个互相隔离的 Python 环境，主界面（Core）保持轻量，不依赖 PyTorch / CUDA：

```powershell
# Windows：一键初始化 Core / AI / MIDI 三个环境
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe main.py
```

```bash
# Linux / 无声卡环境：用模拟信号运行与测试
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

开始之前建议先看看：[贡献指南](CONTRIBUTING.md) · [开发指南](docs/DEVELOPMENT.md) · [架构说明](docs/ARCHITECTURE.md) · [技术决策](docs/DECISIONS.md) · [测试说明](docs/TESTING.md) · [路线图](ROADMAP.md) · [行为准则](CODE_OF_CONDUCT.md)

仓库里的 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 和 `docs/review/` 是和 AI 协作时留下的约束与交接记录，保留下来方便追溯。

</details>

<details>
<summary><b>许可证、隐私与免责声明</b></summary>

<br />

- **许可证**：代码以 [MIT License](LICENSE) 开源。第三方组件及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)，算法的学术出处见 [PROVENANCE.md](docs/PROVENANCE.md)。
- **模型权重**：仓库和发行包都**不包含** AI 模型权重。UVR / MDX-Net、HTDemucs、Basic Pitch 等模型遵循各自的许可证与使用条款，下载前请自行确认。
- **隐私**：所有功能在本地运行，没有遥测，也不上传任何数据，详见 [PRIVACY.md](PRIVACY.md)。
- **关于捕获**：ListenScope 只通过 Windows 标准音频接口「听」你电脑正在播放的声音，不下载、不解密、也不绕过任何 DRM。请遵守当地法律，并尊重你所处理音频的版权。
- **无关联声明**：本项目与任何音乐平台、DAW 或硬件厂商均无关联。文中提到的 QQ 音乐、Cubase、NVIDIA、Windows 等均为各自权利人的商标。
- 本软件按「原样」提供，不附带任何明示或暗示的担保。

</details>

---

## 🙏 致谢

ListenScope 站在很多开源项目和研究者的肩膀上——音频信号处理、音源分离、MIDI 转写，还有 Qt 桌面生态。没有他们的工作，就不会有这个小工具。完整名单与出处见 [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)。

<p align="center">
  <sub>如果 ListenScope 对你有一点点帮助，点个 ⭐ 让更多人看到它吧。</sub>
</p>
