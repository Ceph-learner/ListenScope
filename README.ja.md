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

無料・オフライン・ローカル動作の Windows デスクトップ向け音楽解析・A/B ループ練習・耳コピ補助ワークステーションです。作者と AI アシスタントの協働により開発され、軽量で制御可能なローカル解析環境を目指しています。

---

## 1. スクリーンショット

> **TODO**：UI ブラッシュアップブランチ（#42）のマージ後、最新のスクリーンショットおよびデモ GIF に更新予定です。

---

## 2. 主な機能（検証済み）

- **リアルタイムキャプチャ & 解析**：Windows 標準の WASAPI プロセス単位ループバック（Build ≥ 20348）またはシステムループバックにより再生音声を取得し、波形、FFT/対数スペクトラム、`F0` ピッチ、`-50 ~ +50 cents` 音程バーを表示します。
- **コード・調性・移調**：12-bin Chroma ヒートマップ、長/短三和音判定、ローマ数字度数、12 ステップ履歴、CPU カポ移調、24 調コード練習ダイアログ（試聴・`.mid` 出力対応）を備えています。
- **120 秒履歴 & A/B ループ**：固定 120 秒リングバッファ（`48 kHz / Stereo / float32`）、ドラッグ A/B 指定、`0.5x–1.25x` 音程維持 WSOLA 再生速度変更、12 個のブックマーク、タップメトロノーム、練習 WAV 出力に対応します。
- **ローカル AI ステム分離 & ミキサー（任意）**：独立サブプロセスで 2-Stem（MDX-Net）または 4-Stem（HTDemucs）分離を実行し、6 秒安全チャンクと即時停止（E-STOP）によるメモリ解放、`0–24 dB` ベースソロブースト、FFT-YIN ベース音高解析を提供します。
- **MIDI 出力 & Cubase 対応**：ステムまたは単一 WAV からワンクリックで MIDI 変換し、Steinberg Cubase 互換の SMF Type-0（`480 TPB`）形式で出力します。
- **テーマ & 4 言語対応**：ライト/ダーク切替、複数の内蔵カラーテーマ、中国語（簡体字）/ 英語 / 韓国語 / 日本語のリアルタイム切替に対応します。

---

## 3. システム要件

- **OS**：Windows 10 / 11（64-bit；プロセス単位ループバックには Windows 11 または Windows 10 Build ≥ 20348 が必要です）。
- **実機検証環境**：これまでの実機確認は主に **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM** 環境で行われています。その他の GPU や構成は網羅的に検証されていません。
- **GPU 要件**：**AI ステム分離は任意機能**です。リアルタイムスペクトラム、コード/調性/BPM 解析、A/B 再生、メトロノームは CPU のみで動作します。

---

## 4. ダウンロードとインストール

[Releases](https://github.com/Ceph-learner/ListenScope/releases) からダウンロードできます：

- **インストーラ版**：`ListenScope-Setup-Windows-x64.exe`（アンインストール時に `exports\` を保持）。
- **ポータブル版**：`ListenScope-Core-Windows-x64-Portable.zip`（展開してすぐ実行可能；設定 `settings.json` と出力は同階層に保存）。

**検証と SmartScreen に関する注意**：
- 商用コード署名証明書がないため、初回起動時に Windows SmartScreen 警告が表示される場合があります（「詳細情報 → 実行」で起動できます）。
- ダウンロード後はリリースの `SHA256SUMS.txt` で整合性を確認してください（PowerShell: `Get-FileHash <ファイル名> -Algorithm SHA256`）。
- 公式 Core リリースには **FFmpeg は同梱されていません**。必要に応じてユーザー側で別途導入してください。

---

## 5. クイックスタート

1. `ListenScope.exe` を起動します（GPU なしでリアルタイム解析と A/B 練習を利用できます）。
2. *（任意）* AI 分離や WAV→MIDI を使う場合は、設定画面の **`AI & MIDI 環境`** からローカル PyTorch のスキャンまたは独立環境の自動構築を行います。
3. 上部バーから再生中のアプリを選択し、キャプチャを開始します。

詳しい操作手順や活用例は [ユーザーガイド (docs/USER_GUIDE.en.md)](docs/USER_GUIDE.en.md)（または [中文指南](docs/USER_GUIDE.md)）をご覧ください。

---

## 6. アップデートについて

- 現在は GitHub Releases から最新版を手動でダウンロードして上書き更新してください（ポータブル版では `settings.json`、`exports/`、ローカル環境ディレクトリを保持してください）。
- アプリ内アップデート確認機能は今後のバージョンで計画されています（公開リリース情報のみを取得し、ユーザーデータは送信しません）。

---

## 7. よくある質問（FAQ）

- **NVIDIA GPU がなくても使えますか？** はい。AI 分離は任意機能であり、その他の解析・練習機能は CPU のみで動作します。
- **キャプチャで音が入らない場合は？** 正しい再生プロセスが選択されているか確認するか、システムループバックをお試しください。
- **完全に終了するには？** トレイ格納が有効な場合、タスクトレイアイコンを右クリックして終了してください。

詳細は [FAQ (docs/FAQ.en.md)](docs/FAQ.en.md) および [用語集 (docs/GLOSSARY.en.md)](docs/GLOSSARY.en.md) を参照してください。

---

## 8. 既知の制限

- フレームレスウィンドウでは Windows 11 Snap Layouts（最大化ボタンのホバーメニュー）に未対応です。
- 基準環境（Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM）以外の構成は十分に検証されていません。

---

## 9. コントリビュート

Issue や Pull Request を歓迎します。Core 環境は PyTorch / CUDA / TensorFlow に依存しない 3 環境分離構成を採用しています：

```bash
# Linux / オフスクリーン環境でのテスト
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

詳細は [CONTRIBUTING.md](CONTRIBUTING.md)、[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)、[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、[docs/TESTING.md](docs/TESTING.md)、[ROADMAP.md](ROADMAP.md) をご覧ください。

---

## 10. ライセンス・プライバシー・免責事項

- **ライセンス**：[MIT License](LICENSE)（`Copyright (c) 2026 Ceph-learner and ListenScope contributors`）。サードパーティ表記とライセンス本文は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) および [licenses/](licenses/)、アルゴリズム出典監査は [docs/PROVENANCE.md](docs/PROVENANCE.md) に記載しています。
- **モデル重み**：本リポジトリおよび公式リリースには AI モデルの重みファイルは**含まれません**。各モデル（UVR / MDX-Net、HTDemucs、Basic Pitch）は実行時に上流から取得され、それぞれのライセンス・利用規約が適用されます。
- **免責事項**：
  - 本プロジェクトは Tencent、QQ Music、その他いかなる音楽配信プラットフォームとも無関係です。
  - OS 標準オーディオ API を通じて再生中の音声のみを取得し、DRM の回避・復号・ダウンロードは行いません。
  - 処理する音声の著作権および適用法令の遵守はユーザー自身の責任となります。
  - 本ソフトウェアは「現状のまま」無保証で提供されます。商用利用の場合はご自身で法務・ライセンス評価を行ってください。
- **商標**：QQ Music、Cubase、NVIDIA / RTX、Windows 等の名称は各権利者の商標であり、本プロジェクトと提携関係はありません。
- **プライバシーと AI 協働ファイル**：全機能がローカルで動作しテレメトリはありません（[PRIVACY.md](PRIVACY.md)）。`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`docs/HANDOFF.md`、`docs/AI_COLLABORATION.md`、`docs/review/` は開発制約と協働履歴の記録として保持されています。

---

## 11. 謝辞

音声信号処理、音源分離、MIDI 変換、デスクトップ UI 基盤を支えるオープンソースプロジェクトと研究者の皆様に感謝いたします。詳細は [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) をご覧ください。
