# ListenScope

[简体中文](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 日本語

**無料・オフライン・ローカル動作**の Windows デスクトップ向け音楽解析・A/B ループ・AI ステム分離・耳コピ練習ワークステーションです。

暗号化された音源キャッシュのダウンロードや仮想オーディオドライバの複雑な設定は不要です。音楽プレイヤーやブラウザで再生中の音声を Windows 標準の WASAPI でプロセス単位にキャプチャし、リアルタイムスペクトラム、コード進行、調（Key）、BPM、120 秒区間リピート、ローカル AI ステム分離、Cubase 互換 MIDI エクスポートを提供します。

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope デモ" width="880" />
</p>

---

## クイックスタート（コマンド不要・GUI でワンクリック設定）

一般ユーザーはコマンドプロンプトを使わず、以下の 4 ステップだけですぐに利用できます：

1. **ダウンロード＆インストール**：[Releases](https://github.com/Ceph-learner/ListenScope/releases) から `ListenScope-Setup-Windows-x64.exe` または `ListenScope-Core-Windows-x64-Portable.zip` をダウンロードします。
2. **起動**：`ListenScope.exe` をダブルクリックします。**リアルタイムスペクトラム、コード/調/BPM 解析、120 秒 A/B 変則スピード再生、メトロノームは追加設定なしでそのまま動作**します。
3. **GUI から AI & MIDI をワンクリック導入（任意）**：
   - 右上の **`CONFIG // 設定`** → **`AI & MIDI 環境`** を開きます（下図）。
   - すでに PyTorch / Conda が入っている場合は **ローカル PyTorch スキャン**をクリック；
   - 未導入の場合は **AI + MIDI ワンクリック自動構築**を押すだけで環境が自動セットアップされ、再起動ボタンで即有効になります。
4. **解析開始**：上部の `AUDIO_IN` から再生中のアプリを選び、**`CAPTURE_START`** をクリックします。

<p align="center">
  <img src="docs/images/settings_ai.png" alt="GUI ワンクリック AI & MIDI 設定" width="760" />
</p>

---

## 画面・機能プレビュー

| リアルタイムスペクトラム（ライト・既定） | ダークモード（`VOID // ダーク` 即座切替） |
| :---: | :---: |
| <img src="docs/images/main_light.png" alt="ライトモード" width="440" /> | <img src="docs/images/main_dark.png" alt="ダークモード" width="440" /> |

| コード・調性・チューニングバー＆練習 | 主な機能 |
| :---: | :--- |
| <img src="docs/images/chroma.png" alt="Chroma・コード解析" width="440" /> | • **リアルタイムキャプチャ & 解析**：プロセス単位 WASAPI ループバック（Build ≥ 20348）、波形、FFT/対数スペクトラム、`F0` ピッチ＆`-50 ~ +50 cents` 音程バー。<br>• **コード・調性・カポ連動**：12-bin Chroma ヒートマップ、ローマ数字度数、CPU **カポ/移調**、24 調コード練習ダイアログ（試聴・`.mid` 出力）。<br>• **120 秒 A/B ループ**：固定 120 秒リングバッファ、`0.5x–1.25x` 音程維持 WSOLA 再生速度変更、12 個のブックマーク、タップメトロノーム＆練習 WAV 出力。<br>• **ローカル AI ステム & MIDI**：2-Stem / 4-Stem 分離、**`0–24 dB` ベースソロブースト**、`B0`/`E1` 対応 FFT-YIN、**Cubase 互換 SMF Type-0 (`480 TPB`) MIDI**。 |

---

<details>
<summary><b>開発者向け：ソースからの実行・テスト</b></summary>

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe main.py
```

```bash
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen pytest -q --tb=short
```

</details>

---

## ドキュメント・ライセンス

- [アーキテクチャ (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) · [設計判断 (docs/DECISIONS.md)](docs/DECISIONS.md) · [開発ガイド (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md) · [パッケージング (docs/PACKAGING.md)](docs/PACKAGING.md) · [コントリビュート (CONTRIBUTING.md)](CONTRIBUTING.md)
- [MIT License](LICENSE) · [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
