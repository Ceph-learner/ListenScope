"""Additional Phase 2G UI/status/banner phrase translations for full AST i18n coverage."""

from __future__ import annotations

P2G_PHRASE_MAP: dict[str, dict[str, str]] = {
    "(可实时)": {"en": "(Realtime)", "ko": "(실시간 가능)", "ja": "(リアルタイム可)"},
    ", 支持 sm_120": {"en": ", sm_120 supported", "ko": ", sm_120 지원", "ja": "、sm_120 対応"},
    "// 04 16 步鼓点": {"en": "// 04 16-STEP DRUMS", "ko": "// 04 16스텝 드럼", "ja": "// 04 16ステップドラム"},
    "16 步鼓点概览 · MIDI 保留原始击打时间。": {
        "en": "16-step drum overview · MIDI preserves original hit timing.",
        "ko": "16스텝 드럼 개요 · MIDI는 원본 타격 타이밍을 유지합니다.",
        "ja": "16ステップドラム概要・MIDIは元の打撃タイミングを保持します。",
    },
    "16 步鼓点网格": {"en": "16-Step Drum Grid", "ko": "16스텝 드럼 그리드", "ja": "16ステップドラムグリッド"},
    "2 轨快速分离显存预检": {"en": "2-Stem Quick Split VRAM Gate", "ko": "2-Stem 빠른 분리 VRAM 사전 점검", "ja": "2-Stem 高速分離 VRAM 事前チェック"},
    "4 轨精细分离显存预检": {"en": "4-Stem HQ Split VRAM Gate", "ko": "4-Stem 정밀 분리 VRAM 사전 점검", "ja": "4-Stem 高精細分離 VRAM 事前チェック"},
    "AUDIO_IN // 音源": {"en": "AUDIO_IN // SOURCE", "ko": "AUDIO_IN // 소스", "ja": "AUDIO_IN // 音源"},
    "BS-RoFormer 音质细腻但显存开销显著高于 MDX/HTDemucs；默认关闭以保护 8GB 显存，确认空闲显存充足时可手动勾选。": {
        "en": "BS-RoFormer offers finer quality at much higher VRAM cost than MDX/HTDemucs; disabled by default to protect 8GB VRAM.",
        "ko": "BS-RoFormer는 음질이 뛰어나지만 MDX/HTDemucs보다 VRAM 사용량이 훨씬 많아 8GB VRAM 보호를 위해 기본 비활성화됩니다.",
        "ja": "BS-RoFormer は高音質ですが MDX/HTDemucs より VRAM 消費が大きいため、8GB VRAM 保護のため既定で無効です。",
    },
    "CUDA 可用": {"en": "CUDA Ready", "ko": "CUDA 사용 가능", "ja": "CUDA 利用可能"},
    "FFmpeg 已就绪": {"en": "FFmpeg Ready", "ko": "FFmpeg 준비됨", "ja": "FFmpeg 準備完了"},
    "FFmpeg 未发现 (WAV 可直接分析)": {
        "en": "FFmpeg not found (WAV still supported)",
        "ko": "FFmpeg 없음 (WAV 직접 분석 가능)",
        "ja": "FFmpeg 未検出 (WAV は直接解析可能)",
    },
    "HTDemucs 内部模型分段": {"en": "HTDemucs Internal Segment", "ko": "HTDemucs 내부 세그먼트", "ja": "HTDemucs 内部セグメント"},
    "LISTENSCOPE · 实时频谱": {"en": "LISTENSCOPE · LIVE SPECTRUM", "ko": "LISTENSCOPE · 실시간 스펙트럼", "ja": "LISTENSCOPE · リアルタイムスペクトル"},
    "ListenScope AI 分轨": {"en": "ListenScope AI Stems", "ko": "ListenScope AI 스템 분리", "ja": "ListenScope AI ステム分離"},
    "MIDI 文件 (*.mid *.midi)": {"en": "MIDI Files (*.mid *.midi)", "ko": "MIDI 파일 (*.mid *.midi)", "ja": "MIDI ファイル (*.mid *.midi)"},
    "MISS (仅 WAV 可直读)": {"en": "MISS (WAV only)", "ko": "없음 (WAV만 지원)", "ja": "未検出 (WAV のみ対応)"},
    "Markdown 报告 (*.md);;CSV 明细表 (*.csv)": {
        "en": "Markdown Report (*.md);;CSV Table (*.csv)",
        "ko": "Markdown 보고서 (*.md);;CSV 표 (*.csv)",
        "ja": "Markdown レポート (*.md);;CSV 表 (*.csv)",
    },
    "N/A (未检测到 GPU)": {"en": "N/A (No GPU detected)", "ko": "N/A (GPU 감지 안 됨)", "ja": "N/A (GPU 未検出)"},
    "PyTorch/CUDA 或 ONNX Runtime GPU 环境未通过验证，禁止 GPU AI 推理。": {
        "en": "PyTorch/CUDA or ONNX Runtime GPU environment is not verified; GPU AI inference is blocked.",
        "ko": "PyTorch/CUDA 또는 ONNX Runtime GPU 환경이 검증되지 않아 GPU AI 추론이 차단되었습니다.",
        "ja": "PyTorch/CUDA または ONNX Runtime GPU 環境が未検証のため GPU AI 推論をブロックしました。",
    },
    "RMS (均方根) 反映人耳主观感知的平均响度（单位 dBFS，0 dBFS 为满刻度）。": {
        "en": "RMS reflects perceived average loudness in dBFS (0 dBFS = full scale).",
        "ko": "RMS는 사람이 느끼는 평균 음량을 dBFS 단위로 나타냅니다(0 dBFS = 최대치).",
        "ja": "RMS は聴感上の平均ラウドネスを dBFS で表します（0 dBFS がフルスケール）。",
    },
    "RMS 信号电平，−60 到 0 dBFS": {"en": "RMS level, -60 to 0 dBFS", "ko": "RMS 신호 레벨, -60 ~ 0 dBFS", "ja": "RMS 信号レベル、-60 〜 0 dBFS"},
    "SMTC 自动切歌重置：仅当 Windows 媒体会话 (SMTC) 连续两次确认目标播放器切换了新曲目时，才自动清空和弦轨迹、调性窗口与 BPM，暂停/拖动进度条不会误重置。": {
        "en": "SMTC Auto-Reset: clears chord, key, and BPM history only after Windows SMTC confirms a new track twice; pause/seek will not reset.",
        "ko": "SMTC 자동 곡 전환 리셋: Windows 미디어 세션(SMTC)이 새 곡 전환을 연속 2회 확인할 때만 기록을 초기화합니다.",
        "ja": "SMTC 自動曲切替リセット: Windows SMTC が新曲への切替を2回連続確認した場合のみ履歴をクリアします。",
    },
    "Spotify Basic Pitch 依赖 TensorFlow 2.15（仅支持 Python 3.11），隔离在独立 CPU 环境中既避免与 PyTorch CUDA 冲突，也不会争抢 8GB 显卡显存。": {
        "en": "Spotify Basic Pitch requires TensorFlow 2.15 (Python 3.11 only); isolating it in a separate CPU venv avoids PyTorch CUDA conflicts and saves 8GB VRAM.",
        "ko": "Spotify Basic Pitch는 TensorFlow 2.15(Python 3.11 전용)가 필요하므로 별도 CPU 환경에 격리하여 CUDA 충돌과 8GB VRAM 점유를 방지합니다.",
        "ja": "Spotify Basic Pitch は TensorFlow 2.15（Python 3.11 専用）に依存するため、独立 CPU 環境に隔離して CUDA 競合や 8GB VRAM 圧迫を防ぎます。",
    },
    "[BUSY] 初始化进度:": {"en": "[BUSY] Setup progress:", "ko": "[BUSY] 초기화 진행률:", "ja": "[BUSY] 初期化進捗:"},
    "[BUSY] 正在启动子进程检测 AI Python 环境 (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...": {
        "en": "[BUSY] Probing AI Python environment (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...",
        "ko": "[BUSY] AI Python 환경 점검 중 (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...",
        "ja": "[BUSY] AI Python 環境を検証中 (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...",
    },
    "[BUSY] 正在启动子进程检测独立 CPU MIDI 环境 (Basic Pitch / TensorFlow / pkg_resources / mido)...": {
        "en": "[BUSY] Probing CPU MIDI environment (Basic Pitch / TensorFlow / pkg_resources / mido)...",
        "ko": "[BUSY] CPU MIDI 환경 점검 중 (Basic Pitch / TensorFlow / pkg_resources / mido)...",
        "ja": "[BUSY] CPU MIDI 環境を検証中 (Basic Pitch / TensorFlow / pkg_resources / mido)...",
    },
    "[BUSY] 正在扫描本机所有 Python / Conda / 虚拟环境中的 PyTorch 安装情况...": {
        "en": "[BUSY] Scanning local Python / Conda / venvs for PyTorch installations...",
        "ko": "[BUSY] 로컬 Python / Conda / 가상환경의 PyTorch 설치 스캔 중...",
        "ja": "[BUSY] ローカルの Python / Conda / 仮想環境から PyTorch をスキャン中...",
    },
    "[ERR] 找不到 PowerShell (`pwsh` / `powershell`)。": {
        "en": "[ERR] PowerShell (`pwsh` / `powershell`) not found.",
        "ko": "[ERR] PowerShell (`pwsh` / `powershell`)을 찾을 수 없습니다.",
        "ja": "[ERR] PowerShell (`pwsh` / `powershell`) が見つかりません。",
    },
    "[WARN] 当前非 Windows 系统，不能直接执行 Windows 一键脚本 `scripts/setup_windows.ps1`；在 Windows 11 本机上点击此按钮即可自动安装到软件同级目录。": {
        "en": "[WARN] Non-Windows OS: cannot run `scripts/setup_windows.ps1` directly here; click on Windows 11 to auto-install beside the app.",
        "ko": "[WARN] Windows가 아니므로 `scripts/setup_windows.ps1`을 직접 실행할 수 없습니다. Windows 11에서 실행하면 앱 폴더에 자동 설치됩니다.",
        "ja": "[WARN] Windows 以外の OS のため `scripts/setup_windows.ps1` を直接実行できません。Windows 11 上で押すとアプリ同階層へ自動導入されます。",
    },
    "[低音区]": {"en": "[Bass]", "ko": "[저음역]", "ja": "[低音域]"},
    "[可能转调]": {"en": "[Modulation?]", "ko": "[전조 가능]", "ja": "[転調の可能性]"},
    "[混入警告]": {"en": "[Loopback Warn]", "ko": "[루프백 경고]", "ja": "[ループバック警告]"},
    "· [WARN] 检测到可能转调，建议对比原曲确认调性": {
        "en": "· [WARN] Possible modulation detected; verify against original track",
        "ko": "· [WARN] 전조 가능성이 감지되었습니다. 원곡과 대조해 확인하세요",
        "ja": "· [WARN] 転調の可能性を検出しました。原曲と照合してください",
    },
    "⚠️ 所选 A/B 书签已滚出最近 120s 环形缓冲并自动清理。": {
        "en": "⚠️ Selected A/B bookmark rolled out of the 120s ring buffer and was removed.",
        "ko": "⚠️ 선택한 A/B 북마크가 최근 120초 링 버퍼를 벗어나 자동 정리되었습니다.",
        "ja": "⚠️ 選択した A/B ブックマークは直近 120 秒バッファ外に出たため削除されました。",
    },
    "⚠️ 所选 A/B 书签范围无效，已移除。": {
        "en": "⚠️ Selected A/B bookmark has an invalid range and was removed.",
        "ko": "⚠️ 선택한 A/B 북마크 범위가 유효하지 않아 제거되었습니다.",
        "ja": "⚠️ 選択した A/B ブックマークの範囲が無効なため削除しました。",
    },
    "✅ 一键环境配置已完成并自动保存路径。若未立即刷新或刚安装 Python，可在设置页点击「立即重启」或手动重启应用。": {
        "en": "✅ One-click setup complete and paths saved. Click 'Restart ListenScope Now' in Settings or reopen the app if needed.",
        "ko": "✅ 원클릭 환경 구성이 완료되어 경로가 저장되었습니다. 필요 시 설정에서 '지금 ListenScope 다시 시작'을 누르세요.",
        "ja": "✅ 一括環境構築が完了しパスを保存しました。必要に応じて設定画面の「今すぐ再起動」を押してください。",
    },
    "✅ 已开启自动切歌重置：仅在 SMTC 确认换歌后清空历史，暂停/恢复/拖动进度条不会触发": {
        "en": "✅ Auto track-change reset enabled: clears history only on confirmed SMTC track change.",
        "ko": "✅ 자동 곡 전환 리셋 켜짐: SMTC가 새 곡 전환을 확인할 때만 기록을 초기화합니다.",
        "ja": "✅ 自動曲切替リセット有効: SMTC が曲変更を確定した時のみ履歴をクリアします。",
    },
    "✅ 已重置和弦/调性/BPM 分析历史，实时捕获继续运行。": {
        "en": "✅ Reset chord/key/BPM analysis history; live capture continues.",
        "ko": "✅ 코드/조성/BPM 분석 기록을 초기화했습니다. 실시간 캡처는 계속됩니다.",
        "ja": "✅ コード/調性/BPM 解析履歴をリセットしました（ライブキャプチャ継続中）。",
    },
    "上一首": {"en": "Previous Track", "ko": "이전 곡", "ja": "前の曲"},
    "不可用": {"en": "Unavailable", "ko": "사용 불가", "ja": "利用不可"},
    "不可用 / 未在 Windows 真机验证": {
        "en": "Unavailable / Unverified on live Windows",
        "ko": "사용 불가 / Windows 실기 미검증",
        "ja": "利用不可 / Windows 実機未検証",
    },
    "不存在": {"en": "Missing", "ko": "존재하지 않음", "ja": "存在しません"},
    "为什么独立隔离？将数 GB 的 PyTorch CUDA 放在独立子进程环境中，平时不启动 AI 分轨时主程序内存极低、零显存占用；分轨结束后子进程退出即可 100% 释放显存。": {
        "en": "Why isolate? Keeping multi-GB PyTorch CUDA in an external subprocess keeps idle RAM tiny and VRAM at 0, releasing 100% of VRAM when the worker exits.",
        "ko": "왜 격리하나요? 수 GB의 PyTorch CUDA를 외부 하위 프로세스로 격리해 유휴 메모리와 VRAM을 0으로 유지하고 종료 시 100% 반환합니다.",
        "ja": "なぜ隔離するのか: 数 GB の PyTorch CUDA を別サブプロセスに隔離し、待機時のメモリを最小化、終了時に VRAM を 100% 解放します。",
    },
    "仅 CPU": {"en": "CPU Only", "ko": "CPU 전용", "ja": "CPU のみ"},
    "仅控制 4 轨 HTDemucs 单段推理窗口长度（4–10s，实测默认 6s）。若偶发显存紧张会自动回落，不影响 MDX 二轨。": {
        "en": "Controls 4-stem HTDemucs segment window (4-10s, default 6s); auto-reduces on tight VRAM.",
        "ko": "4-Stem HTDemucs 단일 세그먼트 길이(4~10초, 기본 6초)를 제어합니다.",
        "ja": "4-Stem HTDemucs の推論セグメント長（4〜10秒、既定6秒）を制御します。",
    },
    "优先 GPU": {"en": "Prefer GPU", "ko": "GPU 우선", "ja": "GPU 優先"},
    "伴奏 (Instrumental):": {"en": "Instrumental:", "ko": "반주 (Instrumental):", "ja": "伴奏 (Instrumental):"},
    "低于静音门限": {"en": "Below silence gate", "ko": "무음 게이트 미만", "ja": "無音ゲート未満"},
    "保存": {"en": "Save", "ko": "저장", "ja": "保存"},
    "停止": {"en": "Stop", "ko": "중지", "ja": "停止"},
    "停止实验性近实时分轨": {"en": "Stop Live Separation", "ko": "실시간 분리 중지", "ja": "リアルタイム分離停止"},
    "停止独立节拍器": {"en": "Stop Metronome", "ko": "독립 메트로놈 중지", "ja": "単独メトロノーム停止"},
    "全局调性波动/可能转调": {"en": "Key shift / possible modulation", "ko": "조성 변동 / 전조 가능", "ja": "調性変動/転調の可能性"},
    "关": {"en": "OFF", "ko": "끔", "ja": "オフ"},
    "关闭提示横幅": {"en": "Dismiss banner", "ko": "배너 닫기", "ja": "バナーを閉じる"},
    "关闭窗口": {"en": "Close window", "ko": "창 닫기", "ja": "ウィンドウを閉じる"},
    "内存": {"en": "RAM", "ko": "메모리", "ja": "メモリ"},
    "写出": {"en": "Write", "ko": "쓰기", "ja": "書出"},
    "军鼓": {"en": "Snare", "ko": "스네어", "ja": "スネア"},
    "准备": {"en": "Prepare", "ko": "준비", "ja": "準備"},
    "分轨前内存提醒阈值": {"en": "Pre-Split RAM Warn", "ko": "분리 전 RAM 경고 임계값", "ja": "分離前 RAM 警告しきい値"},
    "分轨混音与 MIDI": {"en": "Stem Mixer & MIDI", "ko": "스템 믹서 & MIDI", "ja": "ステムミキサー & MIDI"},
    "分轨结果已清除。可在历史时间轴重新选择片段。": {
        "en": "Stem results cleared. Select a new range on the timeline.",
        "ko": "스템 분리 결과를 지웠습니다. 타임라인에서 새 구간을 선택하세요.",
        "ja": "ステム分離結果をクリアしました。タイムラインで区間を再選択できます。",
    },
    "分轨运行期间若系统可用内存跌破此水位（默认 2048 MB），主程序会立即终止 AI 子进程并回收内存。": {
        "en": "If available RAM drops below this floor (default 2048 MB) during AI split, the AI subprocess is terminated immediately.",
        "ko": "분리 중 사용 가능 RAM이 이 값(기본 2048 MB) 아래로 떨어지면 AI 하위 프로세스를 즉시 종료합니다.",
        "ja": "分離中に空き RAM がこの値（既定 2048 MB）を下回ると AI サブプロセスを即座に終了します。",
    },
    "初始化完成，已自动写入配置": {
        "en": "Setup finished and configuration saved",
        "ko": "초기화 완료, 설정 자동 저장됨",
        "ja": "初期化完了・設定を自動保存しました",
    },
    "加载模型": {"en": "Load Model", "ko": "모델 로드", "ja": "モデル読込"},
    "另存转录 MIDI 文件": {"en": "Save Transcribed MIDI", "ko": "전사된 MIDI 저장", "ja": "文字起こし MIDI を保存"},
    "只要软件所在目录可写，设置(settings.json)、离线分轨临时目录与 WAV/MIDI 导出均直接放在软件同级目录下，不主动写入 C 盘；仅当安装目录为只读系统盘时才安全回退至用户目录。": {
        "en": "When the app folder is writable, settings.json, temp dirs, and exports stay beside the app (falling back to user home only if read-only).",
        "ko": "앱 폴더에 쓰기 가능하면 settings.json과 임시/내보내기 파일을 앱과 같은 폴더에 저장합니다.",
        "ja": "アプリフォルダが書き込み可能なら settings.json や出力先は同階層に保存され、読み取り専用時のみユーザーフォルダへ退避します。",
    },
    "可用": {"en": "Available", "ko": "사용 가능", "ja": "利用可能"},
    "各项内存与显存指标安全": {"en": "RAM & VRAM healthy", "ko": "RAM/VRAM 지표 양호", "ja": "RAM・VRAM ともに正常"},
    "同级便携存储机制": {"en": "Portable Beside-App Storage", "ko": "포터블 동급 폴더 저장", "ja": "ポータブル同階層保存"},
    "启动 2 轨 (人声 + 伴奏 MDX ONNX) 前要求的最低空闲显存（默认 2560 MB）。": {
        "en": "Minimum free VRAM required before starting 2-stem MDX ONNX (default 2560 MB).",
        "ko": "2-Stem(MDX ONNX) 시작 전 필요한 최소 여유 VRAM(기본 2560 MB).",
        "ja": "2-Stem (MDX ONNX) 開始前に必要な最小空き VRAM（既定 2560 MB）。",
    },
    "启动 4 轨 (人声/鼓/贝斯/其他 HTDemucs) 前要求的最低空闲显存（默认 4300 MB）。": {
        "en": "Minimum free VRAM required before starting 4-stem HTDemucs (default 4300 MB).",
        "ko": "4-Stem(HTDemucs) 시작 전 필요한 최소 여유 VRAM(기본 4300 MB).",
        "ja": "4-Stem (HTDemucs) 開始前に必要な最小空き VRAM（既定 4300 MB）。",
    },
    "和弦与调性": {"en": "Chords & Key", "ko": "코드 & 조성", "ja": "コード・調性"},
    "和弦练习模板": {"en": "Chord Practice Templates", "ko": "코드 연습 템플릿", "ja": "コード練習テンプレート"},
    "和弦（指型）": {"en": "Chord (Voicing)", "ko": "코드 (보이싱)", "ja": "コード（ボイシング）"},
    "固定 120 秒内存环形缓冲区已写入的有效音频时长（上限约 43.95 MiB 原始 PCM，绝不无限增长）。": {
        "en": "Buffered audio duration in the fixed 120s ring buffer (~43.95 MiB PCM cap).",
        "ko": "고정 120초 링 버퍼에 기록된 유효 오디오 길이(최대 약 43.95 MiB).",
        "ja": "固定 120 秒リングバッファに蓄積された有効音声長（上限約 43.95 MiB）。",
    },
    "固定 ±1": {"en": "Fixed ±1", "ko": "고정 ±1", "ja": "固定 ±1"},
    "图像文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)": {
        "en": "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        "ko": "이미지 파일 (*.png *.jpg *.jpeg *.webp *.bmp);;모든 파일 (*)",
        "ja": "画像ファイル (*.png *.jpg *.jpeg *.webp *.bmp);;すべてのファイル (*)",
    },
    "基准测试 / 启动中...": {"en": "Benchmark / Starting...", "ko": "벤치마크 / 시작 중...", "ja": "ベンチマーク / 起動中..."},
    "处理中": {"en": "Processing", "ko": "처리 중", "ja": "処理中"},
    "多声部": {"en": "Polyphonic", "ko": "다성부", "ja": "ポリフォニック"},
    "多声部音频，无单一主音": {"en": "Polyphonic audio, no single fundamental", "ko": "다성부 오디오, 단일 주음 없음", "ja": "ポリフォニック音声（単一主音なし）"},
    "大调": {"en": "Major", "ko": "장조", "ja": "長調"},
    "失败": {"en": "Failed", "ko": "실패", "ja": "失敗"},
    "始终为 Windows 桌面合成器 (DWM)、QQ 音乐/网易云音乐与浏览器预留的显存安全垫（默认 1200 MB）。": {
        "en": "VRAM headroom always reserved for Windows DWM, music players, and browsers (default 1200 MB).",
        "ko": "Windows DWM, 음악 플레이어 및 브라우저를 위해 항상 비워두는 VRAM 여유분(기본 1200 MB).",
        "ja": "Windows DWM・音楽プレーヤー・ブラウザ用に常時確保する VRAM 余裕分（既定 1200 MB）。",
    },
    "字号": {"en": "Font Size", "ko": "글꼴 크기", "ja": "文字サイズ"},
    "存在": {"en": "Present", "ko": "존재함", "ja": "あり"},
    "完成": {"en": "Done", "ko": "완료", "ja": "完了"},
    "实时频谱 · 120s 分轨终端": {"en": "Live Spectrum · 120s Stem Terminal", "ko": "실시간 스펙트럼 · 120s 스템 터미널", "ja": "リアルタイムスペクトル · 120s ステム端末"},
    "实验性 BS-RoFormer 模型开关": {"en": "Experimental BS-RoFormer Toggle", "ko": "실험용 BS-RoFormer 모델 토글", "ja": "実験的 BS-RoFormer モデル切替"},
    "导出 A/B 历史片段 WAV": {"en": "Export A/B Excerpt WAV", "ko": "A/B 구간 WAV 내보내기", "ja": "A/B 区間 WAV エクスポート"},
    "导出 ListenScope 诊断排障压缩包 (.zip)": {
        "en": "Export ListenScope Diagnostics (.zip)",
        "ko": "ListenScope 진단 패키지 내보내기 (.zip)",
        "ja": "ListenScope 診断パッケージ書出 (.zip)",
    },
    "导出扒谱与分析报告": {"en": "Export Transcription Report", "ko": "채보 및 분석 보고서 내보내기", "ja": "採譜・解析レポート書出"},
    "导出混合音轨 WAV": {"en": "Export Mixed WAV", "ko": "믹스 WAV 내보내기", "ja": "ミックス WAV 書出"},
    "导出练习和弦 MIDI": {"en": "Export Practice Chords MIDI", "ko": "연습 코드 MIDI 내보내기", "ja": "練習コード MIDI 書出"},
    "小调": {"en": "Minor", "ko": "단조", "ja": "短調"},
    "尚未转录 MIDI —— 请在上方选择已分轨音轨点击「立即转 MIDI」，或点击音轨右侧「转 MIDI」": {
        "en": "No MIDI yet — select a stem above and click 'Transcribe MIDI', or click 'To MIDI' on any track.",
        "ko": "아직 전사된 MIDI가 없습니다. 위에서 스템을 선택해 '지금 MIDI 변환' 또는 트랙의 'MIDI 변환'을 누르세요.",
        "ja": "MIDI 未変換 — 上でステムを選んで「今すぐ MIDI 変換」または各トラックの「MIDI 変換」を押してください。",
    },
    "局部循环区": {"en": "Loop Range", "ko": "구간 루프", "ja": "区間ループ"},
    "工业标准字体 (已锁定)": {"en": "Industrial Standard Font (Locked)", "ko": "산업 표준 글꼴 (잠금)", "ja": "工業標準フォント (固定)"},
    "已停止": {"en": "Stopped", "ko": "중지됨", "ja": "停止済み"},
    "已停止试听进行。": {"en": "Progression preview stopped.", "ko": "진행 미리듣기를 중지했습니다.", "ja": "進行の試聴を停止しました。"},
    "已关闭自动切歌重置（可随时手动点击「换歌重置」）": {
        "en": "Auto track-change reset disabled (manual Reset Harmony remains available).",
        "ko": "자동 곡 전환 리셋 꺼짐(오른쪽 '화성 리셋'으로 수동 초기화 가능).",
        "ja": "自動曲切替リセット無効（手動「和声リセット」はいつでも使用可能）。",
    },
    "已删除选定 A/B 书签。": {"en": "Deleted selected A/B bookmark.", "ko": "선택한 A/B 북마크를 삭제했습니다.", "ja": "選択した A/B ブックマークを削除しました。"},
    "已取消": {"en": "Canceled", "ko": "취소됨", "ja": "キャンセル済み"},
    "已取消导出 MIDI。": {"en": "MIDI export canceled.", "ko": "MIDI 내보내기가 취소되었습니다.", "ja": "MIDI エクスポートをキャンセルしました。"},
    "已导入本地音频，自动停止实验性实时分轨": {
        "en": "Local audio imported; live separation stopped automatically",
        "ko": "로컬 오디오를 가져와 실험용 실시간 분리를 자동 중지했습니다",
        "ja": "ローカル音声読込に伴いリアルタイム分離を自動停止しました",
    },
    "已急停": {"en": "E-STOPPED", "ko": "비상 중지됨", "ja": "緊急停止済み"},
    "已清除本次分轨、分析和 MIDI 预览。": {
        "en": "Cleared stems, analysis, and MIDI preview.",
        "ko": "이번 스템, 분석 및 MIDI 미리보기를 지웠습니다.",
        "ja": "今回のステム・解析・MIDI プレビューをクリアしました。",
    },
    "已载入单轨分析，自动停止实验性实时分轨": {
        "en": "Loaded single stem for analysis; live separation stopped",
        "ko": "단일 스템 분석 로드로 인해 실시간 분리를 중지했습니다",
        "ja": "単一ステム解析の読込に伴いリアルタイム分離を停止しました",
    },
    "底鼓": {"en": "Kick", "ko": "킥", "ja": "キック"},
    "开": {"en": "ON", "ko": "켬", "ja": "オン"},
    "开启": {"en": "Enabled", "ko": "켜짐", "ja": "有効"},
    "当前 120s 环形缓冲可用音频不足 0.2s，请先捕获或导入音频。": {
        "en": "Ring buffer has < 0.2s of audio; capture or import audio first.",
        "ko": "120초 링 버퍼의 유효 오디오가 0.2초 미만입니다. 먼저 캡처하거나 가져오세요.",
        "ja": "120秒リングバッファの有効音声が 0.2 秒未満です。先にキャプチャまたは読込してください。",
    },
    "当前 120s 环形缓冲可用音频不足 0.5s，无法保存 A/B 书签。": {
        "en": "Ring buffer has < 0.5s of audio; cannot save A/B bookmark.",
        "ko": "120초 링 버퍼의 오디오가 0.5초 미만이라 A/B 북마크를 저장할 수 없습니다.",
        "ja": "120秒リングバッファの音声が 0.5 秒未満のため A/B ブックマークを保存できません。",
    },
    "当前 120s 环形缓冲可用音频不足，请先捕获或导入本地音频。": {
        "en": "Insufficient audio in 120s ring buffer; capture or import audio first.",
        "ko": "120초 링 버퍼의 오디오가 부족합니다. 먼저 캡처하거나 로컬 오디오를 가져오세요.",
        "ja": "120秒リングバッファの音声が不足しています。先にキャプチャまたはローカル音声を読み込んでください。",
    },
    "当前 A/B 区间已失效，请重新设定区间后再保存书签。": {
        "en": "Current A/B range is invalid; set a valid range before saving a bookmark.",
        "ko": "현재 A/B 구간이 유효하지 않습니다. 구간을 다시 설정한 뒤 저장하세요.",
        "ja": "現在の A/B 区間が無効です。区間を再設定してからブックマークを保存してください。",
    },
    "当前分析帧的瞬时最大采样振幅；若接近 0.0 dBFS 说明信号逼近数字削波。": {
        "en": "Instantaneous peak sample level of the current frame; near 0.0 dBFS indicates clipping risk.",
        "ko": "현재 프레임의 순간 최대 피크 레벨입니다. 0.0 dBFS에 가까우면 클리핑 위험이 있습니다.",
        "ja": "現在フレームの瞬間最大ピークレベルです。0.0 dBFS に近いとクリッピングの恐れがあります。",
    },
    "当前分析没有可试听的鼓点。": {
        "en": "No drum hits available to preview in the current analysis.",
        "ko": "현재 분석 결과에 미리 들을 드럼 히트가 없습니다.",
        "ja": "現在の解析結果に試聴可能なドラムヒットがありません。",
    },
    "当前历史环形缓冲尚不足 0.5s，请先捕获一段音频后再分离。": {
        "en": "Ring buffer has < 0.5s of audio; capture some audio before separating.",
        "ko": "히스토리 링 버퍼가 0.5초 미만입니다. 먼저 오디오를 캡처한 뒤 분리하세요.",
        "ja": "履歴リングバッファが 0.5 秒未満です。先に音声をキャプチャしてから分離してください。",
    },
    "当前没有可供深度分析的分轨 WAV 文件。": {
        "en": "No separated stem WAV files available for deep analysis.",
        "ko": "심층 분석할 스템 WAV 파일이 없습니다.",
        "ja": "詳細解析できる分離済みステム WAV ファイルがありません。",
    },
    "当前没有有效的 A/B 选区，请先在下方时间轴选择片段后再分轨。": {
        "en": "No valid A/B selection; select a region on the timeline before separating.",
        "ko": "유효한 A/B 선택 구간이 없습니다. 아래 타임라인에서 구간을 선택한 뒤 분리하세요.",
        "ja": "有効な A/B 選択範囲がありません。下のタイムラインで区間を選択してから分離してください。",
    },
    "当前结果没有独立鼓轨。": {
        "en": "No isolated drum stem in the current result.",
        "ko": "현재 결과에 독립 드럼 스템이 없습니다.",
        "ja": "現在の結果に独立したドラムステムがありません。",
    },
    "当前鼓轨未检测到鼓点。": {
        "en": "No drum hits detected in the drum stem.",
        "ko": "현재 드럼 스템에서 드럼 히트가 감지되지 않았습니다.",
        "ja": "現在のドラムステムからドラムヒットが検出されませんでした。",
    },
    "当系统可用内存 (psutil.available) 低于此值时给出黄色提示，但仍允许继续启动分轨（默认 5120 MB）。": {
        "en": "Shows a yellow warning when available RAM falls below this threshold while still allowing AI jobs (default 5120 MB).",
        "ko": "사용 가능 RAM이 이 값 미만이면 노란색 경고를 표시하지만 분리는 계속 허용합니다(기본 5120 MB).",
        "ja": "空き RAM がこの値を下回ると黄色警告を出しますが、分離開始は許可します（既定 5120 MB）。",
    },
    "当系统可用内存低于此值时拒绝启动新的 AI 分轨任务，防止系统卡死或浏览器崩溃（默认 3072 MB）。": {
        "en": "Blocks new AI jobs when available RAM falls below this threshold to prevent freezes (default 3072 MB).",
        "ko": "사용 가능 RAM이 이 값 미만이면 시스템 멈춤을 막기 위해 새 AI 분리를 차단합니다(기본 3072 MB).",
        "ja": "空き RAM がこの値を下回るとシステム停止を防ぐため新規 AI 分離を拒否します（既定 3072 MB）。",
    },
    "打包版尚未配置独立 Python 3.11 CPU MIDI 解释器 (.venv-midi)": {
        "en": "Frozen build has no standalone Python 3.11 CPU MIDI interpreter (.venv-midi) configured",
        "ko": "패키징 버전에 독립 Python 3.11 CPU MIDI 인터프리터(.venv-midi)가 설정되지 않았습니다",
        "ja": "パッケージ版に独立 Python 3.11 CPU MIDI インタプリタ (.venv-midi) が未設定です",
    },
    "打开已有单轨 WAV 进行 MIDI 转录 (如 bass.wav)": {
        "en": "Open an existing stem WAV for MIDI transcription (e.g. bass.wav)",
        "ko": "기존 단일 스템 WAV를 열어 MIDI로 변환 (예: bass.wav)",
        "ja": "既存の単一ステム WAV を開いて MIDI 変換（例: bass.wav）",
    },
    "扩展 7 和弦": {"en": "Extended 7th Chords", "ko": "확장 7화음", "ja": "拡張セブンスコード"},
    "扫描本机 PyTorch 或一键自动配置独立 Python 运行环境": {
        "en": "Scan local PyTorch or auto-configure isolated Python runtimes",
        "ko": "로컬 PyTorch 스캔 또는 독립 Python 런타임 원클릭 구성",
        "ja": "ローカル PyTorch 検出または独立 Python 環境の一括構築",
    },
    "拒绝新分轨阈值": {"en": "Reject New AI RAM Floor", "ko": "신규 분리 차단 임계값", "ja": "新規分離拒否しきい値"},
    "捕获已停止，实时分轨已关闭": {
        "en": "Capture stopped; live separation turned off",
        "ko": "캡처가 중지되어 실시간 분리가 종료되었습니다",
        "ja": "キャプチャ停止に伴いリアルタイム分離を終了しました",
    },
    "换歌重置 (和弦/调性/BPM)": {
        "en": "Reset Harmony (Chord/Key/BPM)",
        "ko": "화성 리셋 (코드/조성/BPM)",
        "ja": "和声リセット (コード/調性/BPM)",
    },
    "推理": {"en": "Infer", "ko": "추론", "ja": "推論"},
    "播放会话": {"en": "Playback Session", "ko": "재생 세션", "ja": "再生セッション"},
    "支持": {"en": "Supported", "ko": "지원됨", "ja": "対応"},
    "放大横轴": {"en": "Zoom In X", "ko": "가로 확대", "ja": "横軸拡大"},
    "显存": {"en": "VRAM", "ko": "VRAM", "ja": "VRAM"},
    "显存/内存不足，请选择安全恢复策略：": {
        "en": "Low VRAM/RAM — choose a safe recovery action:",
        "ko": "VRAM/RAM 부족 — 안전한 복구 전략을 선택하세요:",
        "ja": "VRAM/RAM 不足 — 安全なリカバリ方法を選択してください:",
    },
    "显存不足": {"en": "Low VRAM", "ko": "VRAM 부족", "ja": "VRAM 不足"},
    "暂无可另存的 MIDI 文件，请先对某个分轨执行「转 MIDI」。": {
        "en": "No MIDI file to save yet; transcribe a stem to MIDI first.",
        "ko": "저장할 MIDI 파일이 없습니다. 먼저 스템에서 'MIDI 변환'을 실행하세요.",
        "ja": "保存できる MIDI ファイルがありません。先にいずれかのステムで「MIDI 変換」を実行してください。",
    },
    "暖砂琥珀 · 白天": {"en": "Warm Sand · Light", "ko": "웜 샌드 · 라이트", "ja": "ウォームサンド・ライト"},
    "最近和弦进行显示方式": {"en": "Recent progression display mode", "ko": "최근 코드 진행 표시 방식", "ja": "直近コード進行の表示形式"},
    "有信号": {"en": "Signal", "ko": "신호 있음", "ja": "信号あり"},
    "未安装": {"en": "Not Installed", "ko": "미설치", "ja": "未インストール"},
    "未检测到": {"en": "Not Detected", "ko": "감지 안 됨", "ja": "未検出"},
    "未检测到稳定调性": {"en": "No stable key detected", "ko": "안정된 조성 미감지", "ja": "安定した調性未検出"},
    "未知错误": {"en": "Unknown error", "ko": "알 수 없는 오류", "ja": "不明なエラー"},
    "未配置独立 Python 3.11 CPU MIDI 解释器 (.venv-midi)": {
        "en": "Standalone Python 3.11 CPU MIDI interpreter (.venv-midi) not configured",
        "ko": "독립 Python 3.11 CPU MIDI 인터프리터(.venv-midi)가 설정되지 않았습니다",
        "ja": "独立 Python 3.11 CPU MIDI インタプリタ (.venv-midi) が未設定です",
    },
    "极光冰蓝 · 白天": {"en": "Aurora Ice · Light", "ko": "오로라 아이스 · 라이트", "ja": "オーロラアイス・ライト"},
    "查看硬件、捕获能力和运行环境": {
        "en": "View hardware, capture capabilities, and runtime paths",
        "ko": "하드웨어, 캡처 기능 및 실행 환경 보기",
        "ja": "ハードウェア・キャプチャ能力・実行環境を確認",
    },
    "标准三和弦": {"en": "Standard Triads", "ko": "표준 3화음", "ja": "基本三和音"},
    "桌面与音乐播放器保底显存": {"en": "DWM & Player VRAM Cushion", "ko": "데스크톱/플레이어 여유 VRAM", "ja": "DWM・プレーヤー用確保 VRAM"},
    "检测调性尚不稳定": {"en": "Key estimate still stabilizing", "ko": "조성 추정 안정화 중", "ja": "調性推定が安定化中"},
    "正在刷新验证环境": {"en": "Refreshing & verifying environments", "ko": "환경 새로고침 및 검증 중", "ja": "環境を再検証中"},
    "正在取消任务并释放显存…": {"en": "Canceling job and freeing VRAM...", "ko": "작업 취소 및 VRAM 해제 중...", "ja": "ジョブ中止と VRAM 解放中..."},
    "正在取消加载并释放显存…": {"en": "Canceling load and freeing VRAM...", "ko": "로드 취소 및 VRAM 해제 중...", "ja": "読込中止と VRAM 解放中..."},
    "正在后台流式导出 A/B 片段 WAV...": {
        "en": "Exporting A/B excerpt WAV in background...",
        "ko": "백그라운드에서 A/B 구간 WAV를 내보내는 중...",
        "ja": "バックグラウンドで A/B 区間 WAV を書出中...",
    },
    "正在后台流式导出混合音轨 WAV...": {
        "en": "Exporting mixed stems WAV in background...",
        "ko": "백그라운드에서 믹스 WAV를 내보내는 중...",
        "ja": "バックグラウンドでミックス WAV を書出中...",
    },
    "正在导入本地音频，请稍候...": {"en": "Importing local audio, please wait...", "ko": "로컬 오디오 가져오는 중...", "ja": "ローカル音声を読み込み中..."},
    "正在导出 A/B 片段，请稍候...": {"en": "Exporting A/B excerpt, please wait...", "ko": "A/B 구간 내보내는 중...", "ja": "A/B 区間をエクスポート中..."},
    "正在导出混音，请稍候...": {"en": "Exporting mix, please wait...", "ko": "믹스 내보내는 중...", "ja": "ミックスをエクスポート中..."},
    "没有足够稳定的音符": {"en": "Not enough stable notes", "ko": "충분히 안정된 음표가 없습니다", "ja": "安定した音符が不足しています"},
    "流式分块与 8GB 显存保护": {"en": "Streaming Chunking & 8GB VRAM Guard", "ko": "스트리밍 청크 및 8GB VRAM 보호", "ja": "ストリーミング分割と 8GB VRAM 保護"},
    "流式载入本地音频片段 (最多截取前 120s)": {
        "en": "Stream-load local audio excerpt (first 120s max)",
        "ko": "로컬 오디오 스트리밍 로드 (최대 앞 120초)",
        "ja": "ローカル音声をストリーム読込（最大先頭 120 秒）",
    },
    "点「分析和弦与节奏」生成和弦时间轴、贝斯音符和鼓点。": {
        "en": "Click 'Analyze Chords & Rhythm' to generate chord timeline, bass notes, and drums.",
        "ko": "'코드 및 리듬 분석'을 눌러 코드 타임라인, 베이스 음표 및 드럼을 생성하세요.",
        "ja": "「コード・リズム解析」を押してコードタイムライン・ベース音・ドラムを生成します。",
    },
    "状态说明:": {"en": "Status Note:", "ko": "상태 설명:", "ja": "状態説明:"},
    "独立 AI 分轨环境说明": {"en": "Isolated AI Environment", "ko": "독립 AI 분리 환경 설명", "ja": "独立 AI 分離環境について"},
    "独立 CPU MIDI 环境说明": {"en": "Isolated CPU MIDI Environment", "ko": "독립 CPU MIDI 환경 설명", "ja": "独立 CPU MIDI 環境について"},
    "用户点击 紧急停止 AI": {"en": "User clicked E-STOP AI", "ko": "사용자가 AI 비상 중지 클릭", "ja": "ユーザーが AI 緊急停止をクリック"},
    "用户触发紧急停止 AI": {"en": "User triggered E-STOP AI", "ko": "사용자가 AI 비상 중지 실행", "ja": "ユーザーが AI 緊急停止を実行"},
    "界面字体": {"en": "UI Font", "ko": "UI 글꼴", "ja": "UI フォント"},
    "石墨靛紫 · 白天": {"en": "Graphite Indigo · Light", "ko": "그래파이트 인디고 · 라이트", "ja": "グラファイトインディゴ・ライト"},
    "移调 / Capo 与转调保护：Capo/移调仅改变和弦、调性与记谱提示的指型展示，底层检测始终锚定实音与实际 MIDI 音高，避免转调后错位；遇到转调歌曲时「调性推测」卡片会亮出 [可能转调] 警告。": {
        "en": "Transpose/Capo changes chord/key display shapes while keeping pitch/MIDI detection anchored to concert pitch; [Modulation?] warns on key changes.",
        "ko": "이조/카포는 표시 운지만 변경하며 실제 음고 및 MIDI 감지는 실음을 기준으로 유지합니다.",
        "ja": "移調/カポは表示上のコード/調性のみを変え、音高と MIDI 検出は実音基準を維持します。",
    },
    "空闲": {"en": "Idle", "ko": "대기", "ja": "待機中"},
    "系统环回": {"en": "System Loopback", "ko": "시스템 루프백", "ja": "システムループバック"},
    "系统环回会重新捕获分轨监听输出。请切换到按进程环回后再开启近实时分轨。": {
        "en": "System Loopback re-records mixer output; switch to Process Loopback before enabling live separation.",
        "ko": "시스템 루프백은 믹서 출력을 다시 녹음합니다. 프로세스별 캡처로 전환한 뒤 실시간 분리를 켜세요.",
        "ja": "システムループバックはミキサー出力を再録音します。プロセス別キャプチャへ切り替えてから有効にしてください。",
    },
    "系统资源与日志": {"en": "System Resources & Logs", "ko": "시스템 리소스 & 로그", "ja": "システムリソース・ログ"},
    "系统默认": {"en": "System Default", "ko": "시스템 기본값", "ja": "システム既定"},
    "紧急停止": {"en": "E-STOP", "ko": "비상 중지", "ja": "緊急停止"},
    "紧急停止 (E-STOP) 内存阈值": {"en": "E-STOP RAM Floor", "ko": "비상 중지 (E-STOP) RAM 임계값", "ja": "緊急停止 (E-STOP) RAM しきい値"},
    "练习速度 BPM": {"en": "Practice Tempo BPM", "ko": "연습 템포 BPM", "ja": "練習テンポ BPM"},
    "经典 · 白天": {"en": "Classic · Light", "ko": "클래식 · 라이트", "ja": "クラシック・ライト"},
    "结束": {"en": "End", "ko": "종료", "ja": "終了"},
    "缩小横轴": {"en": "Zoom Out X", "ko": "가로 축소", "ja": "横軸縮小"},
    "背景色": {"en": "Background", "ko": "배경색", "ja": "背景色"},
    "自定义外观与实时预览": {"en": "Custom Appearance & Live Preview", "ko": "사용자 지정 테마 및 실시간 미리보기", "ja": "外観カスタマイズとライブプレビュー"},
    "试听结束。": {"en": "Preview finished.", "ko": "미리듣기가 종료되었습니다.", "ja": "試聴が終了しました。"},
    "请先停止实验性近实时分轨，系统禁止并行运行多个人工智能分轨任务。": {
        "en": "Stop experimental live separation first; parallel AI separation tasks are blocked.",
        "ko": "먼저 실험용 실시간 분리를 중지하세요. AI 분리 작업의 병렬 실행은 금지되어 있습니다.",
        "ja": "先に実験的リアルタイム分離を停止してください。AI 分離タスクの並列実行は禁止されています。",
    },
    "请先停止系统环回捕获，再试听练习和弦，避免把试听声录入历史。": {
        "en": "Stop System Loopback capture before previewing practice chords to avoid feedback.",
        "ko": "연습 코드 미리듣기 전에 시스템 루프백 캡처를 중지하세요.",
        "ja": "練習コードの試聴前にシステムループバックを停止してください。",
    },
    "请先停止系统环回捕获，再试听鼓点，避免把试听声录入历史。": {
        "en": "Stop System Loopback capture before previewing drums to avoid feedback.",
        "ko": "드럼 미리듣기 전에 시스템 루프백 캡처를 중지하세요.",
        "ja": "ドラム試聴前にシステムループバックを停止してください。",
    },
    "请先停止近实时分轨监听，再试听练习和弦。": {
        "en": "Stop live separation monitoring before previewing practice chords.",
        "ko": "연습 코드 미리듣기 전에 실시간 분리 모니터링을 중지하세요.",
        "ja": "練習コードの試聴前にリアルタイム分離モニターを停止してください。",
    },
    "请先停止近实时分轨监听，再试听鼓点。": {
        "en": "Stop live separation monitoring before previewing drums.",
        "ko": "드럼 미리듣기 전에 실시간 분리 모니터링을 중지하세요.",
        "ja": "ドラム試聴前にリアルタイム分離モニターを停止してください。",
    },
    "请先在上方选择大调或小调练习模板，再试听进行或导出 MIDI。": {
        "en": "Select a major or minor practice template above before previewing or exporting MIDI.",
        "ko": "위에서 장조 또는 단조 연습 템플릿을 먼저 선택한 뒤 미리듣기 또는 MIDI 내보내기를 실행하세요.",
        "ja": "上で長調または短調の練習テンプレートを選択してから試聴または MIDI 書出を行ってください。",
    },
    "请先开始按进程捕获，再开启近实时分轨监听。": {
        "en": "Start per-process capture before enabling live separation.",
        "ko": "실시간 분리를 켜기 전에 먼저 프로세스별 캡처를 시작하세요.",
        "ja": "リアルタイム分離を有効にする前にプロセス別キャプチャを開始してください。",
    },
    "请先点击「深度分析分轨 (和弦/Bass/鼓/旋律)」后再导出扒谱报告。": {
        "en": "Run 'Analyze Chords & Rhythm' before exporting the transcription report.",
        "ko": "채보 보고서를 내보내기 전에 먼저 '코드 및 리듬 분석'을 실행하세요.",
        "ja": "採譜レポートを書き出す前に「コード・リズム解析」を実行してください。",
    },
    "贝斯 · 缺少独立贝斯轨": {"en": "Bass · No isolated bass stem", "ko": "베이스 · 독립 베이스 스템 없음", "ja": "ベース・独立ベースステムなし"},
    "贝斯段内调性/最低音区发生转移": {
        "en": "Bass register / key center shifted in excerpt",
        "ko": "베이스 구간 내 조성/최저음역 이동",
        "ja": "ベース区間内で調性/最低音域が移動",
    },
    "踩镲": {"en": "Hi-Hat", "ko": "하이햇", "ja": "ハイハット"},
    "近实时分轨 [实验]": {"en": "Live Split [Exp]", "ko": "실시간 분리 [실험]", "ja": "ライブ分離 [実験]"},
    "近期和弦不足": {"en": "Not enough recent chords", "ko": "최근 코드가 부족합니다", "ja": "直近のコードが不足しています"},
    "选择分轨转 MIDI": {"en": "Select Stem for MIDI", "ko": "MIDI 변환할 스템 선택", "ja": "MIDI 変換するステムを選択"},
    "选择已分轨音轨转 MIDI": {"en": "Select Separated Stem for MIDI", "ko": "분리된 스템을 선택해 MIDI 변환", "ja": "分離済みステムを選択して MIDI 変換"},
    "选择本地 CUDA cu128 Wheel 目录": {
        "en": "Select Local CUDA cu128 Wheel Directory",
        "ko": "로컬 CUDA cu128 Wheel 폴더 선택",
        "ja": "ローカル CUDA cu128 Wheel フォルダを選択",
    },
    "选择独立 AI Worker Python 解释器": {
        "en": "Select Isolated AI Worker Python Interpreter",
        "ko": "독립 AI Worker Python 인터프리터 선택",
        "ja": "独立 AI Worker Python インタプリタを選択",
    },
    "选择独立 CPU MIDI Python 解释器 (建议 Python 3.11 .venv-midi)": {
        "en": "Select Isolated CPU MIDI Python Interpreter (Python 3.11 .venv-midi)",
        "ko": "독립 CPU MIDI Python 인터프리터 선택 (Python 3.11 .venv-midi 권장)",
        "ja": "独立 CPU MIDI Python インタプリタを選択 (Python 3.11 .venv-midi 推奨)",
    },
    "选择自定义背景图": {"en": "Select Custom Background Image", "ko": "사용자 지정 배경 이미지 선택", "ja": "カスタム背景画像を選択"},
    "配置内存、显存阈值和分轨模型参数": {
        "en": "Configure RAM/VRAM guardrails and stem separation parameters",
        "ko": "RAM/VRAM 보호 임계값 및 분리 모델 파라미터 설정",
        "ja": "RAM・VRAM しきい値と分離モデルパラメータを設定",
    },
    "酸性遥测 · 白天": {"en": "Acid Telemetry · Light", "ko": "애시드 텔레메트리 · 라이트", "ja": "アシッドテレメトリ・ライト"},
    "采用 YIN / 自相关基频算法实时追踪当前最显著音高（显示音名、Hz 频率与音分偏差 cents）。": {
        "en": "Tracks the dominant fundamental pitch in real time using YIN / autocorrelation (note, Hz, cents).",
        "ko": "YIN/자기상관 알고리즘으로 가장 뚜렷한 음고(음이름, Hz, 센트 편차)를 실시간 추적합니다.",
        "ja": "YIN / 自己相関アルゴリズムで現在の主要音高（音名・Hz・セント偏差）をリアルタイム追跡します。",
    },
    "错误": {"en": "Error", "ko": "오류", "ja": "エラー"},
    "长音频会切分为固定秒数重叠分块依次送入 AI 子进程，防止 8GB 显存 / 16GB 内存峰值溢出；实测推荐 6.0s。": {
        "en": "Splits long audio into overlapping fixed-second chunks for the AI worker to prevent 8GB VRAM / 16GB RAM spikes (6.0s recommended).",
        "ko": "긴 오디오를 고정 초 단위 겹침 청크로 나누어 8GB VRAM / 16GB RAM 스파이크를 방지합니다(6.0s 권장).",
        "ja": "長尺音声を固定秒数の重複チャンクに分割し、8GB VRAM / 16GB RAM のスパイクを防ぎます（6.0秒推奨）。",
    },
    "阻塞": {"en": "Blocked", "ko": "차단됨", "ja": "ブロック"},
    "附近没有更安静的过零点，A/B 边界保持原样。": {
        "en": "No quieter zero-crossing nearby; A/B bounds kept unchanged.",
        "ko": "근처에 더 조용한 영교차점이 없어 A/B 경계를 유지합니다.",
        "ja": "近くに静かなゼロクロス点がないため A/B 境界をそのまま維持します。",
    },
    "静音": {"en": "Silent", "ko": "무음", "ja": "無音"},
    "音量: 70%": {"en": "Vol: 70%", "ko": "볼륨: 70%", "ja": "音量: 70%"},
    "默认采用酸性遥测浅色白天主题（锁定标准工业字体与官方配色，字号 11–20px 可调）；切换到其他主题后可自由调节颜色、系统字体并上传自定义背景壁纸。": {
        "en": "Uses Acid Telemetry Light by default (locked industrial font & palette, 11-20px size); switch themes to customize colors, fonts, and wallpapers.",
        "ko": "기본값은 애시드 텔레메트리 라이트 테마이며, 다른 테마로 전환하면 색상·글꼴·배경 이미지를 자유롭게 설정할 수 있습니다.",
        "ja": "既定はアシッドテレメトリ・ライトテーマです。他テーマへ切り替えると色・フォント・背景画像を自由に調整できます。",
    },
    # Issue #37 R2 updater UI strings
    "当前已是最新版本。": {
        "en": "You are already on the latest version.",
        "ko": "이미 최신 버전입니다.",
        "ja": "現在最新バージョンです。",
    },
    "检查更新失败，请检查网络或镜像设置后重试。": {
        "en": "Update check failed. Check your network or mirror settings and try again.",
        "ko": "업데이트 확인에 실패했습니다. 네트워크 또는 미러 설정을 확인 후 다시 시도하세요.",
        "ja": "更新の確認に失敗しました。ネットワークまたはミラー設定を確認して再試行してください。",
    },
    "自动检查更新（每 24 小时最多一次）": {
        "en": "Check for updates automatically (at most once every 24h)",
        "ko": "자동 업데이트 확인 (24시간당 최대 1회)",
        "ja": "自動で更新を確認（24 時間に最大 1 回）",
    },
    "包含预发布版本": {
        "en": "Include prerelease versions",
        "ko": "프리릴리스 버전 포함",
        "ja": "プレリリース版を含める",
    },
    "立即检查": {
        "en": "Check Now",
        "ko": "지금 확인",
        "ja": "今すぐ確認",
    },
    "在线更新:": {
        "en": "Online Updates:",
        "ko": "온라인 업데이트:",
        "ja": "オンライン更新:",
    },
    "可选：GitHub 下载失败时使用的镜像前缀（如 https://gh-proxy.example.com/）": {
        "en": "Optional: mirror prefix used if GitHub download fails (e.g. https://gh-proxy.example.com/)",
        "ko": "선택 사항: GitHub 다운로드 실패 시 사용할 미러 접두사 (예: https://gh-proxy.example.com/)",
        "ja": "任意: GitHub ダウンロード失敗時に使うミラー接頭辞（例: https://gh-proxy.example.com/）",
    },
    "更新下载镜像:": {
        "en": "Update Mirror:",
        "ko": "업데이트 미러:",
        "ja": "更新ミラー:",
    },
    "发现新版本": {
        "en": "New Version Available",
        "ko": "새 버전 출시",
        "ja": "新しいバージョン",
    },
    "暂无更新说明。": {
        "en": "No release notes provided.",
        "ko": "릴리스 노트가 없습니다.",
        "ja": "リリースノートはありません。",
    },
    "跳过此版本": {
        "en": "Skip This Version",
        "ko": "이 버전 건너뛰기",
        "ja": "このバージョンをスキップ",
    },
    "稍后": {
        "en": "Later",
        "ko": "나중에",
        "ja": "あとで",
    },
    "取消下载": {
        "en": "Cancel Download",
        "ko": "다운로드 취소",
        "ja": "ダウンロードをキャンセル",
    },
    "立即更新": {
        "en": "Update Now",
        "ko": "지금 업데이트",
        "ja": "今すぐ更新",
    },
    "正在下载并校验更新包…": {
        "en": "Downloading and verifying update package...",
        "ko": "업데이트 패키지를 다운로드하고 검증하는 중...",
        "ja": "更新パッケージをダウンロードして検証中…",
    },
    "关闭": {
        "en": "Close",
        "ko": "닫기",
        "ja": "閉じる",
    },
    "已取消下载（支持下次断点续传）。": {
        "en": "Download canceled (resumable on next attempt).",
        "ko": "다운로드가 취소되었습니다(다음 시도 시 이어받기 지원).",
        "ja": "ダウンロードをキャンセルしました（次回レジューム対応）。",
    },
    "无法获取校验信息，请稍后重试或手动下载": {
        "en": "Unable to fetch verification checksums. Please try again later or download manually.",
        "ko": "체크섬 정보를 가져올 수 없습니다. 나중에 다시 시도하거나 수동으로 다운로드하세요.",
        "ja": "チェックサム情報を取得できませんでした。しばらくしてから再試行するか手動でダウンロードしてください。",
    },
    "未找到匹配当前版本的安装包，请前往 Releases 页面手动下载。": {
        "en": "No matching package found for this installation. Please download manually from the Releases page.",
        "ko": "현재 설치 유형과 일치하는 패키지를 찾을 수 없습니다. Releases 페이지에서 수동으로 다운로드하세요.",
        "ja": "現在のインストール形式に一致するパッケージが見つかりません。Releases ページから手動でダウンロードしてください。",
    },
    "立即安装更新并退出": {
        "en": "Install Update & Quit",
        "ko": "지금 업데이트 설치 후 종료",
        "ja": "今すぐ更新をインストールして終了",
    },
    "立即应用更新并重启": {
        "en": "Apply Update & Restart",
        "ko": "지금 업데이트 적용 후 다시 시작",
        "ja": "今すぐ更新を適用して再起動",
    },
}

import re as _re

P2G_DYNAMIC_REGEX_RULES: tuple[tuple[_re.Pattern[str], dict[str, str]], ...] = (
    (
        _re.compile(r"^初始化完成，已自动写入配置(?=\s*\|\s*(?:源|Mirror):)"),
        {
            "en": "Setup finished and configuration saved",
            "ko": "초기화 완료, 설정 자동 저장됨",
            "ja": "初期化完了・設定を自動保存しました",
        },
    ),
    (
        _re.compile(r"^源:\s*"),
        {"en": "Mirror: ", "ko": "미러: ", "ja": "ミラー: "},
    ),
    (
        _re.compile(r"\|\s*源:\s*"),
        {"en": "| Mirror: ", "ko": "| 미러: ", "ja": "| ミラー: "},
    ),
    (
        _re.compile(r"^\[ERR\] 找不到初始化脚本:\s*"),
        {"en": "[ERR] Setup script not found: ", "ko": "[ERR] 초기화 스크립트를 찾을 수 없습니다: ", "ja": "[ERR] 初期化スクリプトが見つかりません: "},
    ),
    (
        _re.compile(r"^\[ERR\] 检测失败:\s*"),
        {"en": "[ERR] Probe failed: ", "ko": "[ERR] 점검 실패: ", "ja": "[ERR] 検証失敗: "},
    ),
    (
        _re.compile(r"^\[ERR\] MIDI 环境不可用:\s*"),
        {"en": "[ERR] MIDI environment unavailable: ", "ko": "[ERR] MIDI 환경 사용 불가: ", "ja": "[ERR] MIDI 環境が利用できません: "},
    ),
    (
        _re.compile(r"^\[ERR\] 初始化失败 \(exit=([^)]+)\):"),
        {"en": r"[ERR] Setup failed (exit=\1):", "ko": r"[ERR] 초기화 실패 (exit=\1):", "ja": r"[ERR] 初期化失敗 (exit=\1):"},
    ),
    (
        _re.compile(r"^\[ERR\] 启动初始化脚本失败:\s*"),
        {"en": "[ERR] Failed to launch setup script: ", "ko": "[ERR] 초기화 스크립트 실행 실패: ", "ja": "[ERR] 初期化スクリプトの起動に失敗: "},
    ),
    (
        _re.compile(r"^\[WARN\] 当前在 (.+?) 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。$"),
        {
            "en": r"[WARN] Running on \1: WASAPI Process Loopback and RTX 5060 Ti CUDA are unverified on live Windows.",
            "ko": r"[WARN] \1에서 실행 중: WASAPI Process Loopback 및 RTX 5060 Ti CUDA는 Windows 실기에서 검증되지 않았습니다.",
            "ja": r"[WARN] \1 で実行中: WASAPI Process Loopback と RTX 5060 Ti CUDA は Windows 実機未検証です。",
        },
    ),
    (
        _re.compile(r"^\[OK\] 在本机扫描到 (\d+) 个包含 PyTorch 的 Python 环境（已自动填入最优路径）：$"),
        {
            "en": r"[OK] Found \1 local Python environment(s) with PyTorch (best path auto-filled):",
            "ko": r"[OK] PyTorch가 설치된 로컬 Python 환경 \1개를 찾았습니다(최적 경로 자동 입력):",
            "ja": r"[OK] PyTorch を含むローカル Python 環境を \1 件検出しました（最適パスを自動入力）:",
        },
    ),
    (
        _re.compile(r"^正在对 (.+?) 使用轻量转录。配置独立环境后可用 Basic Pitch。$"),
        {
            "en": r"Using lightweight transcription for \1. Configure the isolated env for Basic Pitch.",
            "ko": r"\1에 경량 전사를 사용 중입니다. 독립 환경을 구성하면 Basic Pitch를 사용할 수 있습니다.",
            "ja": r"\1 に軽量文字起こしを使用しています。独立環境を設定すると Basic Pitch が使えます。",
        },
    ),
    (
        _re.compile(r"^已用 ([\d.]+)s$"),
        {"en": r"Elapsed \1s", "ko": r"경과 \1s", "ja": r"経過 \1秒"},
    ),
    (
        _re.compile(r"^预计剩余 ([\d.]+)s$"),
        {"en": r"ETA \1s", "ko": r"남은 시간 약 \1s", "ja": r"残り約 \1秒"},
    ),
    (
        _re.compile(r"^导出鼓点 MIDI 失败："),
        {"en": "Failed to export drum MIDI: ", "ko": "드럼 MIDI 내보내기 실패: ", "ja": "ドラム MIDI 書出失敗: "},
    ),
    (
        _re.compile(r"^(\d+) 拍$"),
        {"en": r"\1 beats", "ko": r"\1박", "ja": r"\1 拍"},
    ),
    (
        _re.compile(r"^贝斯 · "),
        {"en": "Bass · ", "ko": "베이스 · ", "ja": "ベース · "},
    ),
    (
        _re.compile(r"^BPM:\s*([^|]+)\s*\|\s*2-Stem 无独立鼓轨，切换 4-Stem 可提取 16 步鼓点$"),
        {
            "en": r"BPM: \1 | No isolated drum stem in 2-Stem; switch to 4-Stem for 16-step drums",
            "ko": r"BPM: \1 | 2-Stem에는 독립 드럼 트랙이 없습니다. 4-Stem으로 전환하세요",
            "ja": r"BPM: \1 | 2-Stem には独立ドラムがありません（4-Stem で 16 ステップ抽出可）",
        },
    ),
    (
        _re.compile(r"^BPM:\s*([^|]+)\s*\|\s*鼓点 K=(\d+) / S=(\d+) / H=(\d+)$"),
        {
            "en": r"BPM: \1 | Drums K=\2 / S=\3 / H=\4",
            "ko": r"BPM: \1 | 드럼 K=\2 / S=\3 / H=\4",
            "ja": r"BPM: \1 | ドラム K=\2 / S=\3 / H=\4",
        },
    ),
    (
        _re.compile(r"^拒绝启动 AI 分轨:\s*"),
        {"en": "AI separation rejected: ", "ko": "AI 분리 시작 거부됨: ", "ja": "AI 分離開始を拒否しました: "},
    ),
    (
        _re.compile(r"^❌ 拒绝启动 AI 分轨:\s*"),
        {"en": "❌ AI separation rejected: ", "ko": "❌ AI 분리 시작 거부됨: ", "ja": "❌ AI 分離開始を拒否しました: "},
    ),
    (
        _re.compile(r"^导出待分轨片段失败:\s*"),
        {"en": "Failed to export excerpt for separation: ", "ko": "분리용 구간 내보내기 실패: ", "ja": "分離用区間の書出に失敗: "},
    ),
    (
        _re.compile(r"^导入本地音频失败:\s*"),
        {"en": "Failed to import local audio: ", "ko": "로컬 오디오 가져오기 실패: ", "ja": "ローカル音声の読込に失敗: "},
    ),
    (
        _re.compile(r"^送入分析失败:\s*"),
        {"en": "Failed to send to analysis: ", "ko": "분석 전송 실패: ", "ja": "解析への送信に失敗: "},
    ),
    (
        _re.compile(r"^启动音频捕获失败:\s*"),
        {"en": "Failed to start audio capture: ", "ko": "오디오 캡처 시작 실패: ", "ja": "音声キャプチャの開始に失敗: "},
    ),
    (
        _re.compile(r"系统可用 RAM 极低 \(([\d.]+) MB < ([\d.]+) MB\)，应立即紧急停止 AI 任务"),
        {
            "en": r"Critically low RAM (\1 MB < \2 MB); emergency-stopping AI job",
            "ko": r"사용 가능 RAM 매우 부족(\1 MB < \2 MB); AI 작업 비상 중지 필요",
            "ja": r"空き RAM 極めて不足 (\1 MB < \2 MB)。AI ジョブを緊急停止します",
        },
    ),
    (
        _re.compile(r"系统可用 RAM 不足 \(([\d.]+) MB < ([\d.]+) MB\)，禁止启动新 AI 分轨"),
        {
            "en": r"Insufficient RAM (\1 MB < \2 MB); new AI separation blocked",
            "ko": r"사용 가능 RAM 부족(\1 MB < \2 MB); 새 AI 분리 차단됨",
            "ja": r"空き RAM 不足 (\1 MB < \2 MB)。新規 AI 分離をブロックしました",
        },
    ),
    (
        _re.compile(r"系统可用 RAM 偏紧 \(([\d.]+) MB < ([\d.]+) MB\)"),
        {
            "en": r"RAM tight (\1 MB < \2 MB)",
            "ko": r"사용 가능 RAM 부족 주의(\1 MB < \2 MB)",
            "ja": r"空き RAM 逼迫 (\1 MB < \2 MB)",
        },
    ),
    (
        _re.compile(r"已有 (\d+) 个 AI 分轨任务运行中（硬限制=(\d+)，当前可用 RAM=([\d.]+) MB），禁止并行。"),
        {
            "en": r"\1 AI job already running (hard limit=\2, free RAM=\3 MB); parallel jobs blocked.",
            "ko": r"이미 \1개의 AI 작업이 실행 중입니다(최대=\2, 여유 RAM=\3 MB). 병렬 실행 불가.",
            "ja": r"すでに \1 件の AI ジョブが実行中です（上限=\2、空き RAM=\3 MB）。並列実行不可。",
        },
    ),
    # Issue #37 R2 updater dialog dynamic strings
    (
        _re.compile(r"^发现新版本\s+(.+)$"),
        {
            "en": r"New Version Available: \1",
            "ko": r"새 버전 출시: \1",
            "ja": r"新しいバージョン: \1",
        },
    ),
    (
        _re.compile(r"^当前版本:\s*([^|]+?)\s*\|\s*最新版本:\s*([^|]+?)\s*\|\s*发布日期:\s*(.+)$"),
        {
            "en": r"Current: \1  |  Latest: \2  |  Released: \3",
            "ko": r"현재 버전: \1  |  최신 버전: \2  |  배포일: \3",
            "ja": r"現在: \1  |  最新: \2  |  公開日: \3",
        },
    ),
    (
        _re.compile(r"^正在下载更新包:\s*([\d.]+)\s*/\s*([\d.]+)\s*MB\s*\((\d+)%\)$"),
        {
            "en": r"Downloading update: \1 / \2 MB (\3%)",
            "ko": r"업데이트 다운로드 중: \1 / \2 MB (\3%)",
            "ja": r"更新をダウンロード中: \1 / \2 MB (\3%)",
        },
    ),
    (
        _re.compile(r"^下载完成并通过 SHA256 校验，已保存至:\s*(.+)$"),
        {
            "en": r"Download verified (SHA256 OK), saved to: \1",
            "ko": r"다운로드 및 SHA256 검증 완료, 저장 위치: \1",
            "ja": r"ダウンロード・SHA256 検証完了、保存先: \1",
        },
    ),
    (
        _re.compile(r"^更新包 SHA256 校验失败，已删除损坏文件:\s*(.+)$"),
        {
            "en": r"SHA256 verification failed; corrupted file deleted: \1",
            "ko": r"SHA256 검증 실패, 손상된 파일을 삭제했습니다: \1",
            "ja": r"SHA256 検証に失敗し、破損ファイルを削除しました: \1",
        },
    ),
    (
        _re.compile(r"^更新下载失败:\s*(.+)$"),
        {
            "en": r"Update download failed: \1",
            "ko": r"업데이트 다운로드 실패: \1",
            "ja": r"更新のダウンロードに失敗しました: \1",
        },
    ),
    (
        _re.compile(r"^应用更新失败，请手动安装或重启后重试:\s*"),
        {
            "en": "Failed to apply update; please install manually or restart and retry: ",
            "ko": "업데이트 적용에 실패했습니다. 수동으로 설치하거나 다시 시작한 후 재시도하세요: ",
            "ja": "更新の適用に失敗しました。手動でインストールするか再起動後に再試行してください: ",
        },
    ),
)



# --- Phase 2H Catalog ---
P2H_PHRASE_MAP: dict[str, dict[str, str]] = {
    "# ListenScope 离线分轨与扒谱分析报告": {
        "en": "# ListenScope Offline Separation & Transcription Report",
        "ko": "# ListenScope 오프라인 분리 및 채보 분석 보고서",
        "ja": "# ListenScope オフライン分離・採譜分析レポート",
    },
    "## 1. 全局调性与节拍概览": {
        "en": "## 1. Global Key & Tempo Overview",
        "ko": "## 1. 전체 조성 및 템포 개요",
        "ja": "## 1. 全体キー・テンポ概要",
    },
    "## 2. 时间轴和弦进行表 (Chord Timeline)": {
        "en": "## 2. Chord Progression Timeline",
        "ko": "## 2. 타임라인 코드 진행표 (Chord Timeline)",
        "ja": "## 2. コード進行タイムライン (Chord Timeline)",
    },
    "## 3. Bass 音轨分析": {
        "en": "## 3. Bass Track Analysis",
        "ko": "## 3. 베이스 트랙 분석",
        "ja": "## 3. ベース・トラック分析",
    },
    "## 4. 鼓组 (Drums) 三频段瞬态与 16 步律动表": {
        "en": "## 4. Drums 3-Band Transients & 16-Step Groove Grid",
        "ko": "## 4. 드럼 3밴드 트랜지언트 및 16스텝 그루브 표",
        "ja": "## 4. ドラム 3帯域トランジェント・16ステップグルーヴ表",
    },
    "- **记谱移调 (Transpose)**: `0 半音 (原调实音)`": {
        "en": "- **Notation Transpose**: `0 semitones (Concert Pitch)`",
        "ko": "- **기보 이조 (Transpose)**: `0 반음 (원조 실음)`",
        "ja": "- **記譜移調 (Transpose)**: `0 半音 (実音)`",
    },
    "4-Stem 标准分轨 (HTDemucs)": {
        "en": "4-Stem Standard Separation (HTDemucs)",
        "ko": "4-Stem 표준 분리 (HTDemucs)",
        "ja": "4-Stem 標準分離 (HTDemucs)",
    },
    "A/B 书签结束帧必须大于起始帧。": {
        "en": "A/B bookmark end frame must be greater than start frame.",
        "ko": "A/B 북마크 종료 프레임은 시작 프레임보다 커야 합니다.",
        "ja": "A/B ブックマークの終了フレームは開始フレームより大きくする必要があります。",
    },
    "A/B 选区已过期，请在历史波形上重新选择。": {
        "en": "A/B selection expired; please re-select on the history waveform.",
        "ko": "A/B 선택 영역이 만료되었습니다. 히스토리 파형에서 다시 선택하세요.",
        "ja": "A/B 選択範囲の有効期限が切れました。履歴波形から再選択してください。",
    },
    "A/B 选区结束位置超出了当前历史音频，请重新选择区间。": {
        "en": "A/B selection end exceeds current history audio; please re-select.",
        "ko": "A/B 선택 끝 위치가 현재 히스토리 오디오를 초과했습니다. 다시 선택하세요.",
        "ja": "A/B 選択終了位置が現在の履歴音声を超えています。再選択してください。",
    },
    "AI 分轨任务已取消": {
        "en": "AI separation task cancelled",
        "ko": "AI 분리 작업이 취소되었습니다",
        "ja": "AI 分離タスクがキャンセルされました",
    },
    "AI 分轨任务已取消并清理临时文件": {
        "en": "AI separation task cancelled and temp files cleaned",
        "ko": "AI 분리 작업이 취소되고 임시 파일이 정리되었습니다",
        "ja": "AI 分離タスクがキャンセルされ一時ファイルを削除しました",
    },
    "Basic Pitch 建议仅用于分轨后的 bass / vocals / piano / guitar 单轨；默认禁止直接分析复杂完整混音（传入 allow_full_mix=True 才可强制尝试）。": {
        "en": "Basic Pitch is recommended only for separated bass/vocals/piano/guitar stems; direct full-mix analysis is disabled by default (pass allow_full_mix=True to force).",
        "ko": "Basic Pitch는 분리된 bass/vocals/piano/guitar 단일 스템에만 권장되며, 기본적으로 전체 믹스 직접 분석은 금지됩니다 (allow_full_mix=True 전달 시 강제 시도).",
        "ja": "Basic Pitch は分離後の bass / vocals / piano / guitar 単一ステム専用を推奨します。フルミックスの直接解析はデフォルトで無効です（allow_full_mix=True で強制可）。",
    },
    "GPU AI 环境未就绪": {
        "en": "GPU AI environment not ready",
        "ko": "GPU AI 환경이 준비되지 않았습니다",
        "ja": "GPU AI 環境が未準備です",
    },
    "ListenScope 关闭，清理 AI Worker": {
        "en": "ListenScope closing, cleaning up AI Worker",
        "ko": "ListenScope 종료 중, AI Worker 정리",
        "ja": "ListenScope 終了のため AI Worker をクリーンアップ中",
    },
    "MIDI 通道必须在 0–15 之间。": {
        "en": "MIDI channel must be between 0 and 15.",
        "ko": "MIDI 채널은 0~15 사이여야 합니다.",
        "ja": "MIDI チャンネルは 0〜15 の範囲で指定してください。",
    },
    "PyTorch/CUDA 或 ONNX Runtime GPU 未就绪，拒绝 GPU 基准测试。": {
        "en": "PyTorch/CUDA or ONNX Runtime GPU not ready; GPU benchmark rejected.",
        "ko": "PyTorch/CUDA 또는 ONNX Runtime GPU가 준비되지 않아 GPU 벤치마크가 거부되었습니다.",
        "ja": "PyTorch/CUDA または ONNX Runtime GPU が未準備のため、GPU ベンチマークを拒否しました。",
    },
    "PyTorch/CUDA 或 ONNX Runtime GPU 未就绪，拒绝进入 GPU AI 推理。": {
        "en": "PyTorch/CUDA or ONNX Runtime GPU not ready; GPU AI inference rejected.",
        "ko": "PyTorch/CUDA 또는 ONNX Runtime GPU가 준비되지 않아 GPU AI 추론이 거부되었습니다.",
        "ja": "PyTorch/CUDA または ONNX Runtime GPU が未準備のため、GPU AI 推論を拒否しました。",
    },
    "Worker 异常": {
        "en": "Worker error",
        "ko": "Worker 오류",
        "ja": "Worker エラー",
    },
    r"^([A-Ga-g][#b♯♭]?)\s+(major|minor|大调|小调)$": {
        "en": r"^([A-Ga-g][#b♯♭]?)\s+(major|minor)$",
        "ko": r"^([A-Ga-g][#b♯♭]?)\s+(major|minor|장조|단조)$",
        "ja": r"^([A-Ga-g][#b♯♭]?)\s+(major|minor|長調|短調)$",
    },
    r"^\s*([A-Ga-g][#b♯♭]?)\s*(major|minor|m|maj|大调|小调)?\s*$": {
        "en": r"^\s*([A-Ga-g][#b♯♭]?)\s*(major|minor|m|maj)?\s*$",
        "ko": r"^\s*([A-Ga-g][#b♯♭]?)\s*(major|minor|m|maj|장조|단조)?\s*$",
        "ja": r"^\s*([A-Ga-g][#b♯♭]?)\s*(major|minor|m|maj|長調|短調)?\s*$",
    },
    "⚠️ 底层 WASAPI 退回全系统 Loopback：其他应用声音可能被混入。": {
        "en": "⚠️ Low-level WASAPI fell back to system-wide Loopback: audio from other apps may be mixed in.",
        "ko": "⚠️ 하위 WASAPI가 전체 시스템 Loopback으로 폴백되었습니다: 다른 앱 소리가 섞일 수 있습니다.",
        "ja": "⚠️ 下層 WASAPI がシステム全体の Loopback にフォールバックしました：他アプリの音声が混入する可能性があります。",
    },
    "任务在写入输出阶段被取消": {
        "en": "Task cancelled during output writing",
        "ko": "출력 쓰기 단계에서 작업이 취소되었습니다",
        "ja": "出力書き込み段階でタスクがキャンセルされました",
    },
    "任务在准备阶段被取消": {
        "en": "Task cancelled during preparation",
        "ko": "준비 단계에서 작업이 취소되었습니다",
        "ja": "準備段階でタスクがキャンセルされました",
    },
    "任务在加载模型阶段被取消": {
        "en": "Task cancelled while loading model",
        "ko": "모델 로드 단계에서 작업이 취소되었습니다",
        "ja": "モデル読み込み段階でタスクがキャンセルされました",
    },
    "任务在模型加载完成后被取消": {
        "en": "Task cancelled after model loading completed",
        "ko": "모델 로드 완료 후 작업이 취소되었습니다",
        "ja": "モデル読み込み完了後にタスクがキャンセルされました",
    },
    "全局调性滑动窗口检测到可能转调": {
        "en": "Possible modulation detected by global key sliding window",
        "ko": "전체 조성 슬라이딩 윈도우에서 전조 가능성이 감지되었습니다",
        "ja": "全体キースライディングウィンドウで転調の可能性を検出しました",
    },
    "实时分轨 worker 启动超时": {
        "en": "Live separation worker startup timed out",
        "ko": "실시간 분리 worker 시작 시간 초과",
        "ja": "リアルタイム分離 worker の起動がタイムアウトしました",
    },
    "实时分轨启动已被用户取消": {
        "en": "Live separation startup cancelled by user",
        "ko": "실시간 분리 시작이 사용자에 의해 취소되었습니다",
        "ja": "リアルタイム分離の起動がユーザーによりキャンセルされました",
    },
    "实时分轨基准测试已被取消": {
        "en": "Live separation benchmark cancelled",
        "ko": "실시간 분리 벤치마크가 취소되었습니다",
        "ja": "リアルタイム分離ベンチマークがキャンセルされました",
    },
    "实时分轨基准测试已被紧急停止/取消": {
        "en": "Live separation benchmark emergency-stopped/cancelled",
        "ko": "실시간 분리 벤치마크가 긴급 중지/취소되었습니다",
        "ja": "リアルタイム分離ベンチマークが緊急停止/キャンセルされました",
    },
    "实验功能已停止": {
        "en": "Experimental feature stopped",
        "ko": "실험 기능이 중지되었습니다",
        "ja": "実験機能は停止しました",
    },
    "实验功能已关闭 (默认关闭)": {
        "en": "Experimental feature disabled (off by default)",
        "ko": "실험 기능이 꺼져 있습니다 (기본값 꺼짐)",
        "ja": "実験機能は無効です（デフォルト無効）",
    },
    "实验性实时分轨仅支持 2-stem 模型。": {
        "en": "Experimental live separation only supports 2-stem models.",
        "ko": "실험적 실시간 분리는 2-stem 모델만 지원합니다.",
        "ja": "実験的リアルタイム分離は 2-stem モデルのみ対応しています。",
    },
    "实验性实时分轨已在运行中。": {
        "en": "Experimental live separation is already running.",
        "ko": "실험적 실시간 분리가 이미 실행 중입니다.",
        "ja": "実験的リアルタイム分離は既に実行中です。",
    },
    "实验性实时分轨正在启动或运行基准测试中，请稍候。": {
        "en": "Experimental live separation is starting or benchmarking; please wait.",
        "ko": "실험적 실시간 분리가 시작 중이거나 벤치마크 실행 중입니다. 잠시 기다려 주세요.",
        "ja": "実験的リアルタイム分離を起動中またはベンチマーク実行中です。お待ちください。",
    },
    "实验性近实时分轨仅支持 2-stem (人声 + 伴奏) 模型，不支持 4-stem 模型。": {
        "en": "Experimental near-real-time separation only supports 2-stem (Vocals + Instrumental) models, not 4-stem.",
        "ko": "실험적 준실시간 분리는 2-stem (보컬 + 반주) 모델만 지원하며 4-stem 모델은 지원하지 않습니다.",
        "ja": "実験的ニアリアルタイム分離は 2-stem（ボーカル + 伴奏）モデルのみ対応し、4-stem モデルには非対応です。",
    },
    "导出区间为空，或已被历史缓冲覆盖。": {
        "en": "Export range is empty or already overwritten by history buffer.",
        "ko": "내보내기 구간이 비어 있거나 히스토리 버퍼에 의해 덮어쓰였습니다.",
        "ja": "書き出し範囲が空か、履歴バッファで上書きされました。",
    },
    "导出期间部分音频已被历史缓冲覆盖，请重新选择 A/B 区间。": {
        "en": "Part of the audio was overwritten during export; please re-select the A/B range.",
        "ko": "내보내기 중 일부 오디오가 히스토리 버퍼에 의해 덮어쓰였습니다. A/B 구간을 다시 선택하세요.",
        "ja": "書き出し中に一部の音声が履歴バッファで上書きされました。A/B 範囲を再選択してください。",
    },
    "导出期间音频历史已重置，请重新选择 A/B 区间。": {
        "en": "Audio history was reset during export; please re-select the A/B range.",
        "ko": "내보내기 중 오디오 히스토리가 초기화되었습니다. A/B 구간을 다시 선택하세요.",
        "ja": "書き出し中に音声履歴がリセットされました。A/B 範囲を再選択してください。",
    },
    "已有 AI 分轨任务运行中（硬限制=1），禁止并行。": {
        "en": "An AI separation task is already running (hard limit = 1); parallel jobs disallowed.",
        "ko": "이미 AI 분리 작업이 실행 중입니다 (하드 제한=1). 병렬 실행이 금지됩니다.",
        "ja": "AI 分離タスクが既に実行中です（上限=1）。並列実行は禁止されています。",
    },
    "已有离线 AI 分轨任务运行中（硬限制=1），请先停止或等待其完成。": {
        "en": "An offline AI separation task is already running (hard limit = 1); stop or wait for it first.",
        "ko": "오프라인 AI 분리 작업이 이미 실행 중입니다 (하드 제한=1). 먼저 중지하거나 완료될 때까지 기다리세요.",
        "ja": "オフライン AI 分離タスクが既に実行中です（上限=1）。先に停止するか完了をお待ちください。",
    },
    "建议暂停原播放器（如 QQ 音乐），避免与 ListenScope A/B 回放重音叠加。": {
        "en": "Recommend pausing the source player (e.g., QQ Music) to avoid overlapping with ListenScope A/B playback.",
        "ko": "ListenScope A/B 재생과 소리가 겹치지 않도록 원본 플레이어(예: QQ Music)를 일시정지하는 것이 좋습니다.",
        "ja": "ListenScope の A/B 再生と重ならないよう、元のプレーヤー（QQ 音楽など）を一時停止することをお勧めします。",
    },
    "当前 A/B 选区的原始音频是静音。可拖动 A/B 边界，或重新选择有波形的片段。": {
        "en": "Raw audio in the current A/B selection is silent. Drag A/B handles or select a non-silent segment.",
        "ko": "현재 A/B 선택 영역의 원본 오디오가 무음입니다. A/B 경계를 드래그하거나 파형이 있는 구간을 다시 선택하세요.",
        "ja": "現在の A/B 選択範囲の元音声は無音です。A/B 境界をドラッグするか、波形のある区間を再選択してください。",
    },
    "当前分析没有可导出的鼓点。": {
        "en": "No drum hits available to export in current analysis.",
        "ko": "현재 분석에서 내보낼 수 있는 드럼 타격이 없습니다.",
        "ja": "現在の分析に書き出し可能なドラムヒットがありません。",
    },
    "当前没有可导出的分离音轨。": {
        "en": "No separated stems available to export.",
        "ko": "내보낼 수 있는 분리 스템이 없습니다.",
        "ja": "書き出し可能な分離ステムがありません。",
    },
    "当前没有可导出的和弦进行。": {
        "en": "No chord progression available to export.",
        "ko": "내보낼 수 있는 코드 진행이 없습니다.",
        "ja": "書き出し可能なコード進行がありません。",
    },
    "当前没有已加载的分轨。": {
        "en": "No separated stems currently loaded.",
        "ko": "현재 로드된 분리 스템이 없습니다.",
        "ja": "現在読み込まれている分離ステムがありません。",
    },
    "当前音频输出不可用，请检查系统默认播放设备。": {
        "en": "Audio output unavailable; please check your system default playback device.",
        "ko": "현재 오디오 출력을 사용할 수 없습니다. 시스템 기본 재생 장치를 확인하세요.",
        "ja": "現在オーディオ出力が利用できません。システムの既定再生デバイスを確認してください。",
    },
    "必须指定 --pid 或 --name。": {
        "en": "Must specify --pid or --name.",
        "ko": "--pid 또는 --name을 지정해야 합니다.",
        "ja": "--pid または --name を指定する必要があります。",
    },
    "所选 A/B 片段已滚出最近 120s 环形缓冲，请重新选择区间。": {
        "en": "Selected A/B segment has scrolled out of the recent 120s ring buffer; please re-select.",
        "ko": "선택한 A/B 구간이 최근 120s 링 버퍼를 벗어났습니다. 구간을 다시 선택하세요.",
        "ja": "選択した A/B 区間は直近 120s リングバッファから押し出されました。再選択してください。",
    },
    "捕获源已变化，实时分轨启动已取消。": {
        "en": "Capture source changed; live separation startup cancelled.",
        "ko": "캡처 소스가 변경되어 실시간 분리 시작이 취소되었습니다.",
        "ja": "キャプチャ元が変更されたため、リアルタイム分離の起動をキャンセルしました。",
    },
    "未安装 PyAudioWPatch，无法启用系统 WASAPI Loopback fallback。请运行: pip install PyAudioWPatch": {
        "en": "PyAudioWPatch not installed; cannot enable system WASAPI Loopback fallback. Run: pip install PyAudioWPatch",
        "ko": "PyAudioWPatch가 설치되지 않아 시스템 WASAPI Loopback 폴백을 활성화할 수 없습니다. 실행: pip install PyAudioWPatch",
        "ja": "PyAudioWPatch が未インストールのため、システム WASAPI Loopback フォールバックを有効化できません。実行: pip install PyAudioWPatch",
    },
    "未安装 Spotify `basic-pitch`。请在 AI Worker 环境中安装: pip install basic-pitch[onnx]": {
        "en": "Spotify `basic-pitch` not installed. Install in AI Worker env: pip install basic-pitch[onnx]",
        "ko": "Spotify `basic-pitch`가 설치되지 않았습니다. AI Worker 환경에 설치하세요: pip install basic-pitch[onnx]",
        "ja": "Spotify `basic-pitch` が未インストールです。AI Worker 環境にインストールしてください: pip install basic-pitch[onnx]",
    },
    "未安装 `audio-separator`。请在 AI Worker 环境中安装: pip install audio-separator[gpu]": {
        "en": "`audio-separator` not installed. Install in AI Worker env: pip install audio-separator[gpu]",
        "ko": "`audio-separator`가 설치되지 않았습니다. AI Worker 환경에 설치하세요: pip install audio-separator[gpu]",
        "ja": "`audio-separator` が未インストールです。AI Worker 環境にインストールしてください: pip install audio-separator[gpu]",
    },
    "未安装 `demucs` 或 `audio-separator`。请在 AI Worker 环境安装: pip install demucs audio-separator[gpu]": {
        "en": "`demucs` or `audio-separator` not installed. Install in AI Worker env: pip install demucs audio-separator[gpu]",
        "ko": "`demucs` 또는 `audio-separator`가 설치되지 않았습니다. AI Worker 환경에 설치하세요: pip install demucs audio-separator[gpu]",
        "ja": "`demucs` または `audio-separator` が未インストールです。AI Worker 環境にインストールしてください: pip install demucs audio-separator[gpu]",
    },
    "未安装 onnxruntime-gpu / onnxruntime-directml，无法运行 GPU MDX-ONNX 模型。": {
        "en": "onnxruntime-gpu / onnxruntime-directml not installed; cannot run GPU MDX-ONNX models.",
        "ko": "onnxruntime-gpu / onnxruntime-directml이 설치되지 않아 GPU MDX-ONNX 모델을 실행할 수 없습니다.",
        "ja": "onnxruntime-gpu / onnxruntime-directml が未インストールのため、GPU MDX-ONNX モデルを実行できません。",
    },
    "未安装 proc-tap，无法启动 WASAPI Process Loopback。请运行: pip install proc-tap": {
        "en": "proc-tap not installed; cannot start WASAPI Process Loopback. Run: pip install proc-tap",
        "ko": "proc-tap이 설치되지 않아 WASAPI Process Loopback을 시작할 수 없습니다. 실행: pip install proc-tap",
        "ja": "proc-tap が未インストールのため、WASAPI Process Loopback を起動できません。実行: pip install proc-tap",
    },
    "未找到可供深度分析的音轨 WAV 文件。": {
        "en": "No stem WAV files found for deep analysis.",
        "ko": "심층 분석에 사용할 스템 WAV 파일을 찾을 수 없습니다.",
        "ja": "詳細分析用のステム WAV ファイルが見つかりません。",
    },
    "未找到默认 WASAPI Loopback 输出设备。": {
        "en": "Default WASAPI Loopback output device not found.",
        "ko": "기본 WASAPI Loopback 출력 장치를 찾을 수 없습니다.",
        "ja": "既定の WASAPI Loopback 出力デバイスが見つかりません。",
    },
    "系统 WASAPI Loopback 启动超时。": {
        "en": "System WASAPI Loopback startup timed out.",
        "ko": "시스템 WASAPI Loopback 시작 시간이 초과되었습니다.",
        "ja": "システム WASAPI Loopback の起動がタイムアウトしました。",
    },
    "检查期间所选历史音频已变化，请重新选择 A/B 区间。": {
        "en": "Selected history audio changed during check; please re-select the A/B range.",
        "ko": "검사 중 선택한 히스토리 오디오가 변경되었습니다. A/B 구간을 다시 선택하세요.",
        "ja": "確認中に選択した履歴音声が変更されました。A/B 範囲を再選択してください。",
    },
    "正在完成音轨写入与输出校验...": {
        "en": "Finalizing stem output writing and verification...",
        "ko": "스템 쓰기 및 출력 검증 완료 중...",
        "ja": "ステムの書き込みと出力検証を完了中...",
    },
    "正在运行基准测试 / 初始化...": {
        "en": "Running benchmark / initializing...",
        "ko": "벤치마크 실행 / 초기화 중...",
        "ja": "ベンチマーク実行 / 初期化中...",
    },
    "正在运行基准测试与启动实时分轨...": {
        "en": "Running benchmark and starting live separation...",
        "ko": "벤치마크 실행 및 실시간 분리 시작 중...",
        "ja": "ベンチマーク実行とリアルタイム分離を起動中...",
    },
    "每个和弦至少需要 1 拍。": {
        "en": "Each chord requires at least 1 beat.",
        "ko": "각 코드에는 최소 1박이 필요합니다.",
        "ja": "各コードには少なくとも 1 拍が必要です。",
    },
    "独立 AI 环境 (.venv-ai) 未配置：Windows 打包版不含 PyTorch/CUDA，请在「设置 -> 资源安全阈值 & AI 配置」中指定 .venv-ai\\Scripts\\python.exe。": {
        "en": "Isolated AI env (.venv-ai) not configured: Windows bundle excludes PyTorch/CUDA; specify .venv-ai\\Scripts\\python.exe in Settings -> Resource Limits & AI.",
        "ko": "독립 AI 환경(.venv-ai)이 설정되지 않았습니다: Windows 패키징 버전에는 PyTorch/CUDA가 없으므로 '설정 -> 리소스 안전 임계값 & AI 설정'에서 .venv-ai\\Scripts\\python.exe를 지정하세요.",
        "ja": "独立 AI 環境 (.venv-ai) が未設定です：Windows パッケージ版には PyTorch/CUDA が含まれないため、「設定 -> リソース安全しきい値 & AI 設定」で .venv-ai\\Scripts\\python.exe を指定してください。",
    },
    "独立 AI 环境 (.venv-ai) 未配置：Windows 打包版主程序不包含 PyTorch/ONNX Runtime，请在「设置 -> 资源安全阈值 & AI 配置」中指定 .venv-ai\\Scripts\\python.exe。": {
        "en": "Isolated AI env (.venv-ai) not configured: Windows bundle excludes PyTorch/ONNX Runtime; specify .venv-ai\\Scripts\\python.exe in Settings -> Resource Limits & AI.",
        "ko": "독립 AI 환경(.venv-ai)이 설정되지 않았습니다: Windows 패키징 본체에는 PyTorch/ONNX Runtime이 없으므로 '설정 -> 리소스 안전 임계값 & AI 설정'에서 .venv-ai\\Scripts\\python.exe를 지정하세요.",
        "ja": "独立 AI 環境 (.venv-ai) が未設定です：Windows パッケージ本体には PyTorch/ONNX Runtime が含まれないため、「設定 -> リソース安全しきい値 & AI 設定」で .venv-ai\\Scripts\\python.exe を指定してください。",
    },
    "第一优先级：轻量 2-stem MDX/ONNX，低显存占用、速度快，不借用 Demucs 4轨混合假两轨。": {
        "en": "Priority 1: Lightweight 2-stem MDX/ONNX, low VRAM, fast, without faking 2-stem from 4-stem Demucs.",
        "ko": "1순위: 경량 2-stem MDX/ONNX, 낮은 VRAM 점유, 빠른 속도 (Demucs 4트랙 혼합 방식 미사용).",
        "ja": "第1優先：軽量 2-stem MDX/ONNX、低 VRAM かつ高速（Demucs 4トラック合成の擬似 2-stem ではありません）。",
    },
    "第三优先级：高质量人声分离，显存需求略高于默认低资源 MDX。": {
        "en": "Priority 3: High-quality vocal separation; slightly higher VRAM than default low-resource MDX.",
        "ko": "3순위: 고품질 보컬 분리, 기본 저리소스 MDX보다 VRAM 요구량이 약간 높음.",
        "ja": "第3優先：高品質ボーカル分離、デフォルト低リソース MDX より VRAM 要件がやや高め。",
    },
    "第二优先级：4-stem 标准方案；实测默认 segment=6s，强制 jobs=1, shifts=1, segment<=10s, OOM 时自动降 segment。": {
        "en": "Priority 2: 4-stem standard; measured default segment=6s, enforces jobs=1, shifts=1, segment<=10s, auto-reduces segment on OOM.",
        "ko": "2순위: 4-stem 표준 방안; 실측 기본 segment=6s, jobs=1/shifts=1/segment<=10s 강제, OOM 시 자동 축소.",
        "ja": "第2優先：4-stem 標準方式；実測デフォルト segment=6s、jobs=1/shifts=1/segment<=10s 強制、OOM 時は自動で segment 削減。",
    },
    "第四优先级（默认关闭）：仅在 RTX 5060 Ti 8GB 实测峰值 VRAM/RAM 合格后才建议手动开启。": {
        "en": "Priority 4 (off by default): Enable manually only after peak VRAM/RAM passes on RTX 5060 Ti 8GB.",
        "ko": "4순위 (기본 꺼짐): RTX 5060 Ti 8GB 실측 피크 VRAM/RAM 통과 후에만 수동 활성화를 권장합니다.",
        "ja": "第4優先（デフォルト無効）：RTX 5060 Ti 8GB で実測ピーク VRAM/RAM 合格後にのみ手動有効化を推奨。",
    },
    "等待有效音频输入": {
        "en": "Waiting for valid audio input",
        "ko": "유효한 오디오 입력 대기 중",
        "ja": "有効な音声入力を待機中",
    },
    "紧急停止执行中，当前禁止启动新的 AI 分轨任务。": {
        "en": "Emergency stop in progress; starting new AI separation tasks is currently blocked.",
        "ko": "긴급 중지 실행 중이므로 새 AI 분리 작업을 시작할 수 없습니다.",
        "ja": "緊急停止を実行中のため、新しい AI 分離タスクの起動は禁止されています。",
    },
    "警告：正在对完整混音进行 MIDI 转录，多乐器叠加可能导致大量误检音符。": {
        "en": "Warning: transcribing full mix to MIDI; overlapping instruments may cause many false notes.",
        "ko": "경고: 전체 믹스를 MIDI로 전사 중입니다. 다중 악기 중첩으로 오검출 노트가 많을 수 있습니다.",
        "ja": "警告：フルミックスを MIDI 採譜中です。複数楽器の重なりにより誤検出音符が多くなる場合があります。",
    },
    "请先停止 A/B 播放，再微调边界。": {
        "en": "Please stop A/B playback before fine-tuning boundaries.",
        "ko": "경계를 미세 조정하기 전에 먼저 A/B 재생을 중지하세요.",
        "ja": "境界を微調整する前に A/B 再生を停止してください。",
    },
    "请先在 120s 历史时间轴选择有效的 A/B 片段。": {
        "en": "Please select a valid A/B segment on the 120s history timeline first.",
        "ko": "먼저 120s 히스토리 타임라인에서 유효한 A/B 구간을 선택하세요.",
        "ja": "先に 120s 履歴タイムラインで有効な A/B 区間を選択してください。",
    },
    "请先在历史波形上设定 A/B 区间。": {
        "en": "Please set an A/B range on the history waveform first.",
        "ko": "먼저 히스토리 파형에서 A/B 구간을 설정하세요.",
        "ja": "先に履歴波形で A/B 範囲を設定してください。",
    },
    "请求 GPU HTDemucs 分轨，但当前 torch.cuda.is_available() 为 False。": {
        "en": "Requested GPU HTDemucs separation, but torch.cuda.is_available() is False.",
        "ko": "GPU HTDemucs 분리를 요청했으나 현재 torch.cuda.is_available()가 False입니다.",
        "ja": "GPU HTDemucs 分離が要求されましたが、現在の torch.cuda.is_available() が False です。",
    },
    "通过进程名匹配（目标当前可能尚未产生活跃 WASAPI 音频会话）。": {
        "en": "Matched by process name (target may not have an active WASAPI audio session yet).",
        "ko": "프로세스 이름으로 일치됨 (대상에 아직 활성 WASAPI 오디오 세션이 없을 수 있음).",
        "ja": "プロセス名で一致（対象にまだアクティブな WASAPI 音声セッションがない可能性があります）。",
    },
    "速度 (BPM) 必须为正数。": {
        "en": "Tempo (BPM) must be positive.",
        "ko": "템포 (BPM)는 양수여야 합니다.",
        "ja": "テンポ (BPM) は正の数である必要があります。",
    },
    "采样率必须为正数。": {
        "en": "Sample rate must be positive.",
        "ko": "샘플레이트는 양수여야 합니다.",
        "ja": "サンプリングレートは正の数である必要があります。",
    },
    "音频历史已重置，请重新选择 A/B 区间。": {
        "en": "Audio history reset; please re-select the A/B range.",
        "ko": "오디오 히스토리가 초기화되었습니다. A/B 구간을 다시 선택하세요.",
        "ja": "音声履歴がリセットされました。A/B 範囲を再選択してください。",
    },
    "鼓轨时长无效。": {
        "en": "Invalid drum track duration.",
        "ko": "드럼 트랙 길이가 유효하지 않습니다.",
        "ja": "ドラムトラックの長さが無効です。",
    },
    "（当前使用测试/Core 轻量单音追踪 fallback，非 Spotify Basic Pitch 模型）": {
        "en": "(Using test/Core lightweight monophonic fallback, not Spotify Basic Pitch)",
        "ko": "(Spotify Basic Pitch 모델이 아닌 테스트/Core 경량 단음 추적 폴백 사용 중)",
        "ja": "（Spotify Basic Pitch ではなく、テスト/Core 軽量単音追跡フォールバックを使用中）",
    },
    "🧪 合成测试信号模式（非 Windows 真机 WASAPI 捕获）。": {
        "en": "🧪 Synthetic test signal mode (not real Windows WASAPI capture).",
        "ko": "🧪 합성 테스트 신호 모드 (실제 Windows WASAPI 캡처 아님).",
        "ja": "🧪 合成テスト信号モード（Windows 実機 WASAPI キャプチャではありません）。",
    },
    "用户点击 紧急停止 AI": {
        "en": "User clicked Emergency Stop AI",
        "ko": "사용자가 AI 긴급 중지를 클릭함",
        "ja": "ユーザーが AI 緊急停止をクリックしました",
    },
    "显存/内存不足，请选择安全恢复策略：": {
        "en": "Insufficient VRAM/RAM; please choose a safe recovery strategy:",
        "ko": "VRAM/RAM 부족, 안전한 복구 전략을 선택하세요:",
        "ja": "VRAM/RAM 不足です。安全な復旧方法を選択してください：",
    },
    "已停止": {
        "en": "Stopped",
        "ko": "중지됨",
        "ja": "停止しました",
    },
}

P2H_DYNAMIC_REGEX_RULES: tuple[tuple[_re.Pattern[str], dict[str, str]], ...] = (
    (
        _re.compile(r"^已切换到\s*(.+)$"),
        {
            "en": r"Switched to \1",
            "ko": r"\1(으)로 전환됨",
            "ja": r"\1 に切り替えました",
        },
    ),
    (
        _re.compile(r"^\[兜底\] 系统 WASAPI Loopback · (.+)$"),
        {
            "en": r"[Fallback] System WASAPI Loopback · \1",
            "ko": r"[폴백] 시스템 WASAPI Loopback · \1",
            "ja": r"[フォールバック] システム WASAPI Loopback · \1",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*用户点击 紧急停止 AI$"),
        {
            "en": r"[\1] User clicked Emergency Stop AI",
            "ko": r"[\1] 사용자가 AI 긴급 중지를 클릭함",
            "ja": r"[\1] ユーザーが AI 緊急停止をクリックしました",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*已停止$"),
        {
            "en": r"[\1] Stopped",
            "ko": r"[\1] 중지됨",
            "ja": r"[\1] 停止しました",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*AI 分轨任务已取消$"),
        {
            "en": r"[\1] AI separation task cancelled",
            "ko": r"[\1] AI 분리 작업이 취소되었습니다",
            "ja": r"[\1] AI 分離タスクがキャンセルされました",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*AI 分轨任务已取消并清理临时文件$"),
        {
            "en": r"[\1] AI separation task cancelled and temp files cleaned",
            "ko": r"[\1] AI 분리 작업이 취소되고 임시 파일이 정리되었습니다",
            "ja": r"[\1] AI 分離タスクがキャンセルされ一時ファイルを削除しました",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*实时分轨启动已被用户取消$"),
        {
            "en": r"[\1] Live separation startup cancelled by user",
            "ko": r"[\1] 실시간 분리 시작이 사용자에 의해 취소되었습니다",
            "ja": r"[\1] リアルタイム分離の起動がユーザーによりキャンセルされました",
        },
    ),
    (
        _re.compile(r"^\[([a-z_]+)\]\s*实时分轨基准测试已被紧急停止/取消$"),
        {
            "en": r"[\1] Live separation benchmark emergency-stopped/cancelled",
            "ko": r"[\1] 실시간 분리 벤치마크가 긴급 중지/취소되었습니다",
            "ja": r"[\1] リアルタイム分離ベンチマークが緊急停止/キャンセルされました",
        },
    ),
)

P2G_PHRASE_MAP.update(P2H_PHRASE_MAP)
P2G_DYNAMIC_REGEX_RULES = P2G_DYNAMIC_REGEX_RULES + P2H_DYNAMIC_REGEX_RULES
