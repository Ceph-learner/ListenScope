# ListenScope

简体中文 | [English](README.en.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

**免费、离线、本地运行**的 Windows 桌面听歌分析、A/B 循环与扒谱练习工具。

不需要下载加密音乐缓存，也不需要折腾音频驱动桥接。在 QQ 音乐、网易云音乐、浏览器或任意播放器正常听歌时，ListenScope 直接通过 Windows 标准接口按进程捕获音频流，提供实时频谱、和弦进行、调性、BPM、120 秒回溯选区、本地 AI 分轨和 Cubase 兼容 MIDI 导出。

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope 界面演示" width="880" />
</p>

---

## 快速上手（零命令行 · 图形界面一键配置）

绝大多数用户无需打开命令行或终端，按以下 4 步即可直接使用全部功能：

1. **下载安装**：前往 [Releases](https://github.com/Ceph-learner/ListenScope/releases) 下载安装包 `ListenScope-Setup-Windows-x64.exe`（或免安装便携版 `ListenScope-Core-Windows-x64-Portable.zip`）。
2. **双击启动**：运行 `ListenScope.exe`。**实时频谱、和弦/调性/BPM 识别、120 秒 A/B 慢放循环与节拍器已内置可用**，无需额外配置显卡环境。
3. **图形界面一键配置 AI 分轨与 MIDI（可选）**：
   - 点击右上角 **`CONFIG // 设置`** → 左侧 **`AI 与 MIDI 环境`**（见下图）。
   - 如果电脑里已经装过 PyTorch / Conda 环境，点击 **「扫描本机 PyTorch 环境」** 即可自动识别；
   - 如果尚未安装，直接点击 **「一键自动配置 AI + MIDI」**，软件会自动检测并补齐 Python 与国内高速镜像依赖，完成后点击 **「立即重启 ListenScope 生效」** 即可。
4. **开始听歌扒谱**：在顶栏 `AUDIO_IN // 音源` 下拉框选择正在播放音乐的软件进程（如播放器或浏览器），点击 **`CAPTURE_START // 开始捕获`**。

> 配置文件（`settings.json`）、离线工作区与导出的 WAV / MIDI 默认**保存在软件同级目录**，不往 `C:\` 盘写入垃圾文件。

<p align="center">
  <img src="docs/images/settings_ai.png" alt="设置页一键扫描与自动配置 AI + MIDI" width="760" />
</p>

---

## 界面与功能直观预览

| 实时频谱与波形（临床浅色 · 默认） | 暗夜工业模式（`VOID // 黑夜` 快切） |
| :---: | :---: |
| <img src="docs/images/main_light.png" alt="实时频谱浅色模式" width="440" /> | <img src="docs/images/main_dark.png" alt="实时频谱暗夜模式" width="440" /> |

| 和弦、调性、音准尺与练习弹窗 | 四大核心模块 |
| :---: | :--- |
| <img src="docs/images/chroma.png" alt="和弦与调性分析" width="440" /> | • **实时捕获与频谱**：Windows 进程环回捕获（Build ≥ 20348，无需虚拟声卡），提供实时波形、FFT / 对数频谱、基频 `F0` 与 `-50 ~ +50 cents` 音准刻度条。<br>• **和弦、调性与移调**：12-bin Chroma 热图、和弦与罗马级数实时轨迹、纯 CPU **Capo 移调联动**、24 调和弦练习弹窗（支持合成试听与 `.mid` 导出）。<br>• **120 秒回溯与 A/B 练习**：固定 120s 环形缓冲、拖拽 A/B 选区、`0.5x–1.25x` 不变调变速回放、12 个练习书签、Tap 定速节拍器及练习 WAV 导出。<br>• **本地 AI 分轨与混音**：独立子进程按需运行 2-Stem / 4-Stem 分离、**`0–24 dB` 贝斯独听增益**、FFT-YIN 贝斯最低音（低至 `B0`/`E1`）与 **Cubase 兼容 SMF Type-0 (`480 TPB`) MIDI 导出**。 |

---

## 主题与多语言

- 默认启用 **酸性遥测（Acid Telemetry · 临床浅色）** 双模工业视觉，顶栏支持 `VOID // 黑夜` 与 `LIGHT // 白天` 一键切换。
- 同时提供 **经典、极光冰蓝、石墨靛紫、暖砂琥珀** 主题（非酸性主题开放本机字体、自定义配色与背景壁纸上传），支持 **简体中文 / English / 한국어 / 日本語** 实时切换与无边框圆角窗口。

---

<details>
<summary><b>开发者选项：从源码运行与环境架构</b>（普通用户请直接使用上方安装包）</summary>

为保持主界面轻量流畅（无需显卡即可使用全部实时分析与 A/B 练习功能），项目采用三环境隔离设计：

```text
ListenScope/
├── core/         # 配置与同级便携路径、多语言 (zh/en/ko/ja)、外观模型、本机 PyTorch 扫描、资源守卫与诊断打包
├── audio/        # WASAPI 进程/系统环回捕获、120s 固定环形缓冲、WSOLA 变速、节拍器、和弦/鼓点试听与四轨混音引擎
├── analysis/     # 纯 CPU 频谱/Chroma/和弦/调性/BPM、FFT-YIN 贝斯与转调分析、Cubase SMF Type-0 MIDI 导出
├── ai/           # 离线分轨模型注册表、流式分块守护与独立 AI 子进程管理
├── separation/   # 2-Stem MDX-ONNX 与 4-Stem HTDemucs 后端
├── streaming/    # 实验性近实时 2-Stem 监听（默认关闭）
├── ui/           # PySide6 + PyQtGraph 桌面界面、酸性遥测样式引擎、紧凑 [?] 说明徽标与设置面板
├── packaging/    # PyInstaller 打包规范与 requirements-ai / requirements-midi 依赖约束
├── scripts/      # Windows 环境初始化 (setup_windows.ps1)、硬件自检与 Inno Setup 安装脚本
└── docs/         # 架构说明、技术决策、开发指南与打包文档
```

```powershell
# Windows 源码初始化（推荐使用 PowerShell 7 在短路径目录如 E:\LS 运行）
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe main.py
```

```bash
# Linux / 无声卡模拟信号与自动化测试
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen pytest -q --tb=short
```

</details>

---

## 文档导航

- [架构设计 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) & [技术决策 (docs/DECISIONS.md)](docs/DECISIONS.md)
- [开发与测试指南 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md)
- [Windows 打包与环境配置 (docs/PACKAGING.md)](docs/PACKAGING.md)
- [贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md)

---

## 开源协议、致谢与反馈

- 本项目基于 [MIT License](LICENSE) 开源；所集成的第三方模型与开源库均保留各自原有许可协议，详见 [致谢与来源 (ACKNOWLEDGMENTS.md)](ACKNOWLEDGMENTS.md)。
- ListenScope 与文中提及的任何第三方音乐播放器、DAW 或硬件厂商均无隶属或商业合作关系；各商标归其各自所有者所有。
- 如果 ListenScope 对你的听歌、练琴或扒谱有帮助，欢迎在 GitHub 点一颗 ⭐ **Star**，或在 [Issues](https://github.com/Ceph-learner/ListenScope/issues) 中提交问题与建议。
