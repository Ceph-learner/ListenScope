# 算法与数据来源审计（PROVENANCE — 草稿）

> **说明**：本文档为 Issue #37 `R1-9` 的来源审计草稿，记录 ListenScope 所使用核心算法、音乐理论轮廓数据及第三方模型调用的学术出处与实现方式。一般认为算法思想与公开论文中的数值轮廓不受著作权保护，具体代码实现受著作权保护；以下结论均基于对仓库代码的静态核查，措辞限定为「未发现复制」，不构成法律或专利意见（商业场景使用请自行评估）。

---

## 一、算法与数据来源总表

| 算法或数据 | 学术出处（论文 / 作者 / 年份） | 本项目实现位置与方式 | 是否参考具体开源代码 | 参考/调用代码许可证 | 核查结论 |
|---|---|---|---|---|---|
| **YIN 基频估计** | Alain de Cheveigné & Hideki Kawahara, *"YIN, a fundamental frequency estimator for speech and music"*, JASA 111(4):1917–1930, 2002 | [`analysis/yin.py`](../analysis/yin.py)、[`analysis/pitch.py`](../analysis/pitch.py)（基于 NumPy/SciPy 自写 CMNDF + 抛物线插值） | 否（按论文公式自写） | N/A | 未发现复制 GPL/AGPL 实现 |
| **WSOLA 时域变速不变调** | Werner Verhelst & Marc Roelands, *"An overlap-add technique based on waveform similarity (WSOLA) for high quality time-scale modification of speech"*, IEEE ICASSP 1993 | [`audio/playback.py`](../audio/playback.py)（基于 NumPy 自写相关性对齐 OLA） | 否（按论文算法自写） | N/A | 未发现复制 Rubber Band / Audacity 代码 |
| **调性轮廓：Krumhansl–Kessler** | Carol L. Krumhansl, *Cognitive Foundations of Musical Pitch*, Oxford University Press, 1990（Krumhansl–Schmuckler 1986） | [`analysis/key_detection.py`](../analysis/key_detection.py) `"krumhansl"`（论文公开数值表 + 自写余弦/皮尔逊匹配） | 否（论文数值） | N/A | 未发现复制 |
| **调性轮廓：Temperley (1999)** | David Temperley, *"What's Key for Key? The Krumhansl-Schmuckler Key-Finding Algorithm Reconsidered"*, Music Perception 17(1):65–100, 1999 | [`analysis/key_detection.py`](../analysis/key_detection.py) `"keyfinder"` *(命名待改为 `"temperley1999"` 并保留别名)* | 否（数值为 Temperley 1999 论文轮廓，**非** libKeyFinder 代码） | N/A | 未发现复制 libKeyFinder（GPL-3）代码；需更名避免误解 |
| **调性轮廓：Albrecht & Shanahan (2013)** | Joshua D. Albrecht & Daniel Shanahan, *"The Use of Large Corpora to Train a New Type of Key-Finding Algorithm"*, Music Perception 31(1):59–67, 2013 | [`analysis/key_detection.py`](../analysis/key_detection.py) `"albrecht"`（论文公开数值表） | 否（论文数值） | N/A | 未发现复制 |
| **调性轮廓：Shaath (2011)** | Ibrahim Shaath, *"Estimation of key in digital music recordings"*, MSc Thesis, Birkbeck, University of London, 2011 | [`analysis/key_detection.py`](../analysis/key_detection.py) `"shaath"`（论文公开 12 维轮廓数值） | 否（仅采用论文公开 12 维数值，未使用 libKeyFinder C++ 代码） | N/A | 未发现复制 libKeyFinder（GPL-3）代码 |
| **色度提取（Chroma）与和弦模板匹配** | Takuya Fujishima, *"Realtime Chord Recognition of Musical Sound: a System Using Common Lisp Music"*, ICMC 1999；经典 STFT/对数频带折叠与三和弦/七和弦/转位模板 | [`analysis/chroma.py`](../analysis/chroma.py)、[`analysis/chords.py`](../analysis/chords.py)（基于 NumPy 自写） | 否（自写） | N/A | 未发现复制 |
| **谱通量 Onset 与自相关 BPM / 半倍速消歧** | Simon Dixon, *"Onset Detection Revisited"*, DAFx 2006；标准半波整流谱通量 + FFT 自相关 + 对数正态速度先验 | [`analysis/tempo.py`](../analysis/tempo.py)、[`analysis/stem_analyzer.py`](../analysis/stem_analyzer.py)（基于 NumPy 自写） | 否（自写） | N/A | 未发现复制 Essentia / aubio 代码 |
| **AI 2-Stem 分轨（MDX-Net）** | Minseok Kim et al., *"KUIELab-MDX-Net"*, 2021（arXiv:2111.12203） | [`separation/mdx_backend.py`](../separation/mdx_backend.py)（通过 `audio-separator` / `onnxruntime` 运行时调用，仓库不含权重） | 调库 | MIT（`audio-separator` / `onnxruntime`）；权重由用户运行时下载 | 仓库不含模型权重；README/ACKNOWLEDGMENTS 提示用户核对权重条款 |
| **AI 4-Stem 分轨（HTDemucs）** | Simon Rouard et al., *"Hybrid Transformers for Music Source Separation"*, ICASSP 2023 | [`separation/demucs_backend.py`](../separation/demucs_backend.py)（通过 `demucs` / `torch` 运行时调用，仓库不含权重） | 调库 | MIT（`demucs`）/ BSD-3（`torch`） | 仓库不含模型权重 |
| **单轨转 MIDI（Basic Pitch）** | Rachel M. Bittner et al., *"A Lightweight Instrument-Agnostic Model for Polyphonic Note Transcription and Multipitch Estimation"*, ICASSP 2022 | [`analysis/midi_transcription.py`](../analysis/midi_transcription.py)（通过 `basic-pitch` / `mido` 独立环境调用，仓库不含权重） | 调库 | Apache-2.0（`basic-pitch`）/ MIT（`mido`） | 仓库不含模型权重 |
| **设置页分组布局思路 & 图标** | PyQt-Fluent-Widgets 公开示例（仅参考信息架构与分组思路）；Lucide 图标集 | [`ui/settings_dialog.py`](../ui/settings_dialog.py)（原生 PySide6 自写）、[`ui/assets/settings/`](../ui/assets/settings/) | 布局思路参考，未复制 GPL 代码；图标使用 Lucide | PyQt-Fluent-Widgets 为 GPLv3（未引入/未复制）；Lucide 为 ISC（许可证保留于 `ui/assets/settings/LICENSE.txt`） | 未发现复制 PyQt-Fluent-Widgets 代码 |

---

## 二、GPL / AGPL 项目特征静态核查记录

使用 `rg` 在全部生产源码（`ai/`、`analysis/`、`audio/`、`core/`、`separation/`、`streaming/`、`ui/`、`main.py`）检索以下项目具有辨识度的名称、类名、函数名与注释关键字：
- 检索词：`libkeyfinder`、`keyfinder`、`essentia`、`aubio`、`rubberband`、`rubber band`、`qfluentwidgets`、`FluentWindow`、`SettingCardGroup`、`audacity`、`madmom`。
- **结果**：
  - `essentia` / `aubio` / `rubberband` / `qfluentwidgets` / `FluentWindow` / `SettingCardGroup` / `audacity` / `madmom`：**0 处命中**。
  - `keyfinder`：**仅 1 处命中**（`analysis/key_detection.py:29-30`），其数值经核对为 **Temperley (1999)** 论文轮廓（`[5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]`），不涉及 libKeyFinder 代码。**待办（R1-9 实现阶段）**：将键名重命名为 `"temperley1999"`，保留 `"keyfinder"` 兼容别名并在注释中写明 Temperley (1999) 出处。
- **综合结论**：在当前仓库生产源码中**未发现**从上述 GPL / AGPL 项目直接复制代码的情况。

---

## 三、Phase 3（Issue #33）拟引入库的许可证风险前置审查

| 拟评估库 | 许可证 | 风险与兼容结论（MIT 项目） |
|---|---|---|
| **madmom** | 代码 BSD-2-Clause，但**预训练模型权重据称采用 CC BY-NC-SA**（禁止商业用途且具传染性） | **不可随 MIT 发行包分发或默认启用**；如未来需要，仅能作为用户自选、手动安装的外部可选插件，并在文档中明确非商业限制。 |
| **Rubber Band** | GPL-2.0+ 或商业双许可 | **与 MIT 闭源/宽容再分发不兼容**；若集成进发行包会导致整体受 GPL 约束。建议维持自研 WSOLA 或仅调用用户本机外部 CLI（不捆绑）。 |
| **Essentia** | AGPL-3.0（或商业许可） | **与 MIT 不兼容**；不得引入依赖或复制到本仓库。 |
