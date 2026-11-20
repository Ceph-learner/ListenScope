"""Comprehensive 4-language (zh/en/ko/ja) UI phrases, dynamic patterns, and HelpBadge catalog."""

from __future__ import annotations

import re

# Additional exact UI phrase translations covering MainWindow, Mixer, Chroma, Spectrum,
# Live Engine, Resources, AppearanceDialog, SettingsDialog, and ChordPracticeDialog.
EXTRA_PHRASE_MAP: dict[str, dict[str, str]] = {
    # --- MainWindow & General ---
    "外观主题": {"en": "Appearance & Theme", "ko": "외관 테마", "ja": "外観とテーマ"},
    "ListenScope 设置": {"en": "ListenScope Settings", "ko": "ListenScope 설정", "ja": "ListenScope 設定"},
    "练习和弦 // CHORD PRACTICE": {
        "en": "CHORD PRACTICE",
        "ko": "CHORD PRACTICE // 코드 연습",
        "ja": "CHORD PRACTICE // コード練習",
    },
    "设置 / 系统状态": {"en": "Settings / Status", "ko": "설정 / 시스템 상태", "ja": "設定 / システム状態"},
    "紧急停止 AI": {"en": "E-Stop AI", "ko": "AI 긴급 정지", "ja": "AI 緊急停止"},
    "优先 GPU（未就绪）": {"en": "Prefer GPU (Not Ready)", "ko": "GPU 우선 (미준비)", "ja": "GPU 優先 (未準備)"},
    "优先 GPU（已就绪）": {"en": "Prefer GPU (Ready)", "ko": "GPU 우선 (준비됨)", "ja": "GPU 優先 (準備完了)"},
    "扩展和弦 (maj7/m7/7/sus4)": {
        "en": "Extended Chords (maj7/m7/7/sus4)",
        "ko": "확장 코드 (maj7/m7/7/sus4)",
        "ja": "拡張コード (maj7/m7/7/sus4)",
    },
    "0.5x (半速扒谱)": {"en": "0.5x (Half Speed)", "ko": "0.5x (반속 채보)", "ja": "0.5x (半速耳コピ)"},
    "1.0x (原速)": {"en": "1.0x (Normal)", "ko": "1.0x (원속)", "ja": "1.0x (等倍)"},
    "2-Stem 低显存默认 (MDX-Net ONNX)": {
        "en": "2-Stem Low-VRAM Default (MDX-Net ONNX)",
        "ko": "2-Stem 저VRAM 기본 (MDX-Net ONNX)",
        "ja": "2-Stem 低VRAM既定 (MDX-Net ONNX)",
    },
    "2-Stem 低显存默认 (MDX-Net ONNX) [MDX-ONNX]": {
        "en": "2-Stem Low-VRAM Default (MDX-Net ONNX) [MDX-ONNX]",
        "ko": "2-Stem 저VRAM 기본 (MDX-Net ONNX) [MDX-ONNX]",
        "ja": "2-Stem 低VRAM既定 (MDX-Net ONNX) [MDX-ONNX]",
    },
    "2-Stem 高质量人声 (MDX-Net Voc FT)": {
        "en": "2-Stem High-Quality Vocals (MDX-Net Voc FT)",
        "ko": "2-Stem 고음질 보컬 (MDX-Net Voc FT)",
        "ja": "2-Stem 高品質ボーカル (MDX-Net Voc FT)",
    },
    "2-Stem 高质量人声 (MDX-Net Voc FT) [MDX-ONNX]": {
        "en": "2-Stem High-Quality Vocals (MDX-Net Voc FT) [MDX-ONNX]",
        "ko": "2-Stem 고음질 보컬 (MDX-Net Voc FT) [MDX-ONNX]",
        "ja": "2-Stem 高品質ボーカル (MDX-Net Voc FT) [MDX-ONNX]",
    },
    "原调 / 实音 (0)": {"en": "Concert Pitch (0)", "ko": "원키 / 실음 (0)", "ja": "原調 / 実音 (0)"},
    "降半音 / Eb调弦 (+1)": {"en": "Half-Step Down / Eb (+1)", "ko": "반음 내림 / Eb 튜닝 (+1)", "ja": "半音下げ / Ebチューニング (+1)"},
    "降B乐器 (+2: 小号/单簧管)": {"en": "Bb Instrument (+2: Trumpet/Clarinet)", "ko": "Bb 악기 (+2: 트럼펫/클라리넷)", "ja": "Bb管 (+2: トランペット/クラリネット)"},
    "F调圆号 (+7)": {"en": "F Horn (+7)", "ko": "F 호른 (+7)", "ja": "Fホルン (+7)"},
    "降E乐器 (+9: 中音萨克斯)": {"en": "Eb Instrument (+9: Alto Sax)", "ko": "Eb 악기 (+9: 알토 색소폰)", "ja": "Eb管 (+9: アルトサックス)"},
    "倒退 ": {"en": "From -", "ko": "시작 -", "ja": "開始 -"},
    "至倒退 ": {"en": "To -", "ko": "끝 -", "ja": "終了 -"},
    "书签名称 (如 副歌/Solo，可留空)": {
        "en": "Bookmark label (e.g. Chorus/Solo, optional)",
        "ko": "북마크 이름 (예: 후렴/솔로, 선택)",
        "ja": "ブックマーク名 (例: サビ/ソロ・任意)",
    },
    "实时频谱与波形": {"en": "Realtime Spectrum & Waveform", "ko": "실시간 스펙트럼 & 파형", "ja": "リアルタイムスペクトル＆波形"},
    "实时波形": {"en": "Live Waveform", "ko": "실시간 파형", "ja": "リアルタイム波形"},
    "FFT 频谱": {"en": "FFT Spectrum", "ko": "FFT 스펙트럼", "ja": "FFT スペクトル"},
    "频带能量": {"en": "Band Energy", "ko": "대역 에너지", "ja": "帯域エネルギー"},
    "最近时频图": {"en": "Recent Spectrogram", "ko": "최근 스펙트로그램", "ja": "直近スペクトログラム"},
    "平均电平 · RMS": {"en": "AVG LEVEL · RMS", "ko": "평균 레벨 · RMS", "ja": "平均レベル · RMS"},
    "峰值电平": {"en": "PEAK LEVEL", "ko": "피크 레벨", "ja": "ピークレベル"},
    "主音高": {"en": "MAIN PITCH", "ko": "기본 음고", "ja": "基本ピッチ"},
    "历史缓冲": {"en": "RING BUFFER", "ko": "히스토리 버퍼", "ja": "履歴バッファ"},
    "12-BIN CHROMA // 实时色度分布": {
        "en": "12-BIN CHROMA // LIVE DISTRIBUTION",
        "ko": "12-BIN CHROMA // 실시간 크로마 분포",
        "ja": "12-BIN CHROMA // リアルタイムクロマ分布",
    },
    "CHROMA HEATMAP // 有界时序热图 (120s)": {
        "en": "CHROMA HEATMAP // BOUNDED TIMELINE (120s)",
        "ko": "CHROMA HEATMAP // 유계 시계열 히트맵 (120s)",
        "ja": "CHROMA HEATMAP // 有界時系列ヒートマップ (120s)",
    },
    "N (静音)": {"en": "N (Silent)", "ko": "N (무음)", "ja": "N (無音)"},
    "说明: 调性中心(Key)与调号(Key Signature)并不完全等同，关系大小调/调式混合可能共用调号。": {
        "en": "Note: Key center differs from Key Signature; relative major/minor and modal interchange share signatures.",
        "ko": "참고: 조성 중심(Key)과 조표(Key Signature)는 동일하지 않으며, 나란한조/모드 혼용은 조표를 공유할 수 있습니다.",
        "ja": "注: 調性中心(Key)と調号(Key Signature)は必ずしも一致せず、平行調やモード借用で同じ調号を共有します。",
    },
    # --- GroupBoxes & Telemetry Headers ---
    "AI SEPARATION // 分轨任务队列": {
        "en": "AI SEPARATION // JOB QUEUE",
        "ko": "AI SEPARATION // 분리 작업 큐",
        "ja": "AI SEPARATION // 分離タスクキュー",
    },
    "[GUARDRAIL] 显存 / 内存不足 (GPU OOM) 恢复选项": {
        "en": "[GUARDRAIL] GPU VRAM / RAM OOM Recovery Options",
        "ko": "[GUARDRAIL] VRAM / RAM 부족 (GPU OOM) 복구 옵션",
        "ja": "[GUARDRAIL] VRAM / RAM 不足 (GPU OOM) 復旧オプション",
    },
    "BOUNDED DIAGNOSTIC LOG // 有界运行日志 (仅保留最近 500 条)": {
        "en": "BOUNDED DIAGNOSTIC LOG // LAST 500 ENTRIES",
        "ko": "BOUNDED DIAGNOSTIC LOG // 유계 실행 로그 (최근 500건)",
        "ja": "BOUNDED DIAGNOSTIC LOG // 有界診断ログ (直近500件)",
    },
    "MEMORY + VRAM GRID // 实时资源监控 (主 RAM / AI RAM / RTX 5060 Ti 8GB VRAM)": {
        "en": "MEMORY + VRAM GRID // REALTIME RESOURCE TELEMETRY (8GB VRAM GUARDRAIL)",
        "ko": "MEMORY + VRAM GRID // 실시간 리소스 모니터 (주 RAM / AI RAM / 8GB VRAM)",
        "ja": "MEMORY + VRAM GRID // リアルタイム資源監視 (主RAM / AI RAM / 8GB VRAM)",
    },
    "PERFORMANCE LEDGER // 本地 AI 性能记录 (logs/performance/)": {
        "en": "PERFORMANCE LEDGER // LOCAL AI BENCHMARK LOGS (logs/performance/)",
        "ko": "PERFORMANCE LEDGER // 로컬 AI 성능 기록 (logs/performance/)",
        "ja": "PERFORMANCE LEDGER // ローカルAI性能ログ (logs/performance/)",
    },
    "MIX BALANCE // 实时人声与伴奏混音比例": {
        "en": "MIX BALANCE // LIVE VOCAL & INSTRUMENTAL RATIO",
        "ko": "MIX BALANCE // 실시간 보컬/반주 믹스 비율",
        "ja": "MIX BALANCE // リアルタイム ボーカル＆伴奏バランス",
    },
    "STREAM TELEMETRY // 实时分轨监控指标": {
        "en": "STREAM TELEMETRY // LIVE SEPARATION METRICS",
        "ko": "STREAM TELEMETRY // 실시간 분리 모니터링 지표",
        "ja": "STREAM TELEMETRY // リアルタイム分離メトリクス",
    },
    "主题风格 · 字体字号 · 多语言与交互": {
        "en": "Theme Presets · Typography · Language & Interactions",
        "ko": "테마 프리셋 · 글꼴 크기 · 다국어 및 인터랙션",
        "ja": "テーマ・フォントサイズ・多言語とインタラクション",
    },
    "硬件资源遥测 · 性能日志 · 诊断包": {
        "en": "Hardware Telemetry · Performance Ledger · Diagnostics",
        "ko": "하드웨어 텔레메트리 · 성능 로그 · 진단 패키지",
        "ja": "ハードウェア監視・性能ログ・診断パッケージ",
    },
    "实验性近实时人声 / 伴奏分离": {
        "en": "Experimental Near-Realtime Vocal / Instrumental Separation",
        "ko": "실험적 준실시간 보컬 / 반주 분리",
        "ja": "実験的 準リアルタイム ボーカル / 伴奏分離",
    },
    "实验性近实时二轨分离（人声 + 伴奏）。监听前请选择按进程捕获，系统环回会把监听输出再次录入。\n速度基准用于判断模型能否跟上实时播放。资源告警时自动停止分轨，频谱分析继续运行。": {
        "en": "Experimental near-realtime 2-stem split (Vocals + Instrumental). Select Process Loopback before monitoring so System Loopback will not re-record output.\nRun the RTF speed benchmark first to verify realtime throughput. Automatically pauses on resource alerts while spectrum analysis stays active.",
        "ko": "실험적 준실시간 2-Stem 분리(보컬 + 반주)입니다. 모니터링 전 프로세스 캡처를 선택하세요(시스템 루프백은 출력이 다시 녹음됨).\n속도 벤치마크로 실시간 처리 가능 여부를 먼저 확인하세요. 리소스 경고 시 자동 중지되며 스펙트럼 분석은 유지됩니다.",
        "ja": "実験的な準リアルタイム2ステム分離（ボーカル＋伴奏）です。モニター前にプロセス別キャプチャを選択してください（システムループバックでは出力が再録音されます）。\n速度ベンチマークでリアルタイム追従可否を確認でき、資源警告時は自動停止してスペクトル解析のみ継続します。",
    },
    # --- Mixer & Subtabs ---
    "// 01 和弦与节奏": {"en": "// 01 Chords && Rhythm", "ko": "// 01 코드 && 리듬", "ja": "// 01 コードとリズム"},
    "// 02 MIDI 卷帘": {"en": "// 02 Piano Roll", "ko": "// 02 MIDI 피아노 롤", "ja": "// 02 MIDI ピアノロール"},
    "// 03 MIDI 音符": {"en": "// 03 MIDI Notes", "ko": "// 03 MIDI 노트", "ja": "// 03 MIDI ノート"},
    "// 04 16 步鼓点": {"en": "// 04 16-Step Drums", "ko": "// 04 16스텝 드럼", "ja": "// 04 16ステップドラム"},
    "分轨音轨槽位 · 待载入": {
        "en": "Stem Track Bay · Standby",
        "ko": "스템 트랙 슬롯 · 대기 중",
        "ja": "ステムトラックスロット · 待機中",
    },
    "在下方 120s 历史缓冲选定 A/B 区间后，点击「AI 2-Stem 分轨」或「AI 4-Stem 分轨」；分离后的人声 / 伴奏 / 贝斯 / 鼓组独立波形轨、M/S 独听与单轨转 MIDI 按钮将在此处就位。": {
        "en": "Select an A/B region on the 120s history buffer below and trigger 'AI 2-Stem' or 'AI 4-Stem'. Isolated Vocals / Instrumental / Bass / Drums waveform rows, M/S solo controls, and stem-to-MIDI actions will dock here.",
        "ko": "아래 120초 히스토리 버퍼에서 A/B 구간을 선택한 뒤 'AI 2-Stem 분리' 또는 'AI 4-Stem 분리'를 실행하세요. 분리된 보컬 / 반주 / 베이스 / 드럼 파형 트랙과 M/S 솔로 및 MIDI 변환 버튼이 이곳에 배치됩니다.",
        "ja": "下部の120秒履歴バッファでA/B区間を選択し、「AI 2-Stem 分離」または「AI 4-Stem 分離」を実行してください。分離後のボーカル／伴奏／ベース／ドラム波形トラックとM/S・MIDI変換ボタンがここに配置されます。",
    },
    "空闲：请在下方 120s 历史时间轴选择片段并启动 2-Stem 或 4-Stem 分轨": {
        "en": "Idle: Select an A/B excerpt on the 120s history timeline below and launch 2-Stem or 4-Stem AI separation.",
        "ko": "대기 중: 아래 120초 히스토리 타임라인에서 구간을 선택하고 2-Stem 또는 4-Stem 분리를 시작하세요.",
        "ja": "待機中: 下部の120秒履歴タイムラインで区間を選び、2-Stem または 4-Stem 分離を開始してください。",
    },
    "分离触发 OOM，已安全清理残留内存与临时文件，请选择处理方式：": {
        "en": "OOM triggered during separation. Residual memory and temp files were safely cleared. Choose a recovery action:",
        "ko": "분리 중 OOM이 발생했습니다. 잔여 메모리와 임시 파일을 안전하게 정리했습니다. 복구 방법을 선택하세요:",
        "ja": "分離中にOOMが発生しました。残留メモリと一時ファイルは安全に解放済みです。復旧方法を選択してください:",
    },
    "1. 降低 segment 重试": {"en": "1. Retry Smaller Segment", "ko": "1. 세그먼트 축소 재시도", "ja": "1. セグメント縮小で再試行"},
    "2. 切换轻量 2-Stem 模型": {"en": "2. Switch to Light 2-Stem", "ko": "2. 경량 2-Stem 모델 전환", "ja": "2. 軽量 2-Stem へ切替"},
    "3. 改用 CPU fallback": {"en": "3. Use CPU Fallback", "ko": "3. CPU 폴백 사용", "ja": "3. CPU フォールバック"},
    "导出扒谱报告": {"en": "Export Sheet Report", "ko": "채보 리포트 내보내기", "ja": "耳コピレポート出力"},
    "导出鼓点 MIDI": {"en": "Export Drum MIDI", "ko": "드럼 MIDI 내보내기", "ja": "ドラム MIDI 出力"},
    "打开单轨 WAV…": {"en": "Open Stem WAV…", "ko": "단일 WAV 열기…", "ja": "単一 WAV を開く…"},
    "试听鼓点": {"en": "Preview Drums", "ko": "드럼 미리듣기", "ja": "ドラム試聴"},
    "分轨完成后，可在这里分析和弦、调性、贝斯音符和鼓点。": {
        "en": "After stem separation completes, analyze chords, key, bass lowest notes, and drum grooves here.",
        "ko": "스템 분리가 완료되면 여기에서 코드, 조성, 베이스 최저음 및 드럼 패턴을 분석할 수 있습니다.",
        "ja": "ステム分離の完了後、ここでコード・調性・ベース最低音・ドラムパターンを解析できます。",
    },
    "分析含独立鼓轨的分轨结果后，这里会显示 16 步鼓点。": {
        "en": "After analyzing a separation with an isolated drums stem, the 16-step drum groove grid will appear here.",
        "ko": "독립 드럼 스템이 포함된 분리 결과를 분석하면 16스텝 드럼 그리드가 표시됩니다.",
        "ja": "独立ドラムステムを含む分離結果を解析すると、16ステップのドラムグリッドが表示されます。",
    },
    "尚未转录。点轨道右侧「转 MIDI」，或打开已有单轨 WAV。": {
        "en": "Not transcribed yet. Click 'To MIDI' on a stem row or open an existing single-stem WAV file.",
        "ko": "아직 변환되지 않았습니다. 트랙 오른쪽의 'MIDI 변환'을 누르거나 단일 WAV 파일을 여세요.",
        "ja": "未転写です。各トラック右の「MIDI変換」を押すか、既存の単一WAVを開いてください。",
    },
    "实时和弦追踪: -": {"en": "Live Chord Track: -", "ko": "실시간 코드 추적: -", "ja": "リアルタイムコード追跡: -"},
    "Loop Scope: 全曲": {"en": "Loop Scope: Full Track", "ko": "루프 범위: 전체", "ja": "ループ範囲: 全曲"},
    # --- Resource & Live Engine ---
    "主进程 RAM:": {"en": "Core Process RAM:", "ko": "메인 프로세스 RAM:", "ja": "メインプロセス RAM:"},
    "系统可用 / 总 RAM:": {"en": "System Free / Total RAM:", "ko": "시스템 가용 / 총 RAM:", "ja": "システム空き / 総 RAM:"},
    "GPU 空闲 / 总 VRAM:": {"en": "GPU Free / Total VRAM:", "ko": "GPU 여유 / 총 VRAM:", "ja": "GPU 空き / 総 VRAM:"},
    "GPU 利用率:": {"en": "GPU Utilization:", "ko": "GPU 사용률:", "ja": "GPU 使用率:"},
    "音频捕获队列:": {"en": "Audio Capture Queue:", "ko": "오디오 캡처 큐:", "ja": "音声キャプチャキュー:"},
    "AI 待处理 / 分块缓冲:": {"en": "AI Pending / Chunk Buffer:", "ko": "AI 대기 / 청크 버퍼:", "ja": "AI 待機 / チャンクバッファ:"},
    "当前 AI 模型 / 任务:": {"en": "Active AI Model / Job:", "ko": "현재 AI 모델 / 작업:", "ja": "実行中 AI モデル / タスク:"},
    "资源保护状态:": {"en": "Guardrail Status:", "ko": "리소스 보호 상태:", "ja": "資源保護ステータス:"},
    "状态说明: 正常": {"en": "Status: Normal", "ko": "상태 설명: 정상", "ja": "状態: 正常"},
    "日志与性能摘要严格有界；如在 Windows 遇到 CUDA/WASAPI 故障可一键导出脱敏诊断包：": {
        "en": "Logs and performance ledgers are strictly bounded. Export a sanitized diagnostics bundle if CUDA/WASAPI issues occur on Windows:",
        "ko": "로그와 성능 기록은 엄격히 크기가 제한됩니다. Windows에서 CUDA/WASAPI 문제 발생 시 비식별 진단 패키지를 내보낼 수 있습니다:",
        "ja": "ログと性能要約は上限管理されています。WindowsでCUDA/WASAPI不具合時は匿名化診断パッケージを出力できます:",
    },
    "开启实验性近实时分轨": {"en": "Start Experimental Live Split", "ko": "실험적 준실시간 분리 시작", "ja": "実験的 準リアルタイム分離を開始"},
    "运行 RTF 速度基准测试": {"en": "Run RTF Speed Benchmark", "ko": "RTF 속도 벤치마크 실행", "ja": "RTF 速度ベンチマーク実行"},
    "人声 (Vocals):": {"en": "Vocals:", "ko": "보컬 (Vocals):", "ja": "ボーカル (Vocals):"},
    "伴奏 (Instrumental):": {"en": "Instrumental:", "ko": "반주 (Instrumental):", "ja": "伴奏 (Instrumental):"},
    "状态: 已关闭 (默认关闭)": {"en": "Status: Off (Default)", "ko": "상태: 꺼짐 (기본값)", "ja": "状態: オフ (既定)"},
    "延迟: 0.0 ms": {"en": "Latency: 0.0 ms", "ko": "지연: 0.0 ms", "ja": "遅延: 0.0 ms"},
    "输出缓冲: 0.00 s": {"en": "Output Buffer: 0.00 s", "ko": "출력 버퍼: 0.00 s", "ja": "出力バッファ: 0.00 s"},
    "RAM (主/Worker): -": {"en": "RAM (Core/Worker): -", "ko": "RAM (메인/워커): -", "ja": "RAM (主/ワーカー): -"},
    "空闲 VRAM / GPU%: -": {"en": "Free VRAM / GPU%: -", "ko": "여유 VRAM / GPU%: -", "ja": "空き VRAM / GPU%: -"},
    "基准测试结果: 尚未运行": {"en": "Benchmark Result: Not Run Yet", "ko": "벤치마크 결과: 미실행", "ja": "ベンチマーク結果: 未実行"},
    "输入跳段 0 次 | 输出溢出丢弃 0 帧 | 输出重缓冲 0 次 | 声卡报告欠载 0 次": {
        "en": "Input Skips: 0 | Output Drops: 0 frames | Rebuffers: 0 | Audio Underruns: 0",
        "ko": "입력 스킵 0회 | 출력 드롭 0프레임 | 리버퍼 0회 | 오디오 언더런 0회",
        "ja": "入力スキップ 0回 | 出力ドロップ 0フレーム | 再バッファ 0回 | 欠落 0回",
    },
    # --- AppearanceDialog ---
    "经典": {"en": "Classic", "ko": "클래식", "ja": "クラシック"},
    "石墨靛紫": {"en": "Graphite", "ko": "그래파이트", "ja": "グラファイト"},
    "暖砂琥珀": {"en": "Warm Sand", "ko": "웜 샌드", "ja": "ウォームサンド"},
    "白天": {"en": "Light", "ko": "라이트", "ja": "ライト"},
    "黑夜": {"en": "Dark", "ko": "다크", "ja": "ダーク"},
    "主题模式": {"en": "Theme Mode", "ko": "테마 모드", "ja": "テーマモード"},
    "交互与引导": {"en": "Interaction & Help", "ko": "인터랙션 및 가이드", "ja": "操作とガイド"},
    "交互与引导:": {"en": "Interaction & Help:", "ko": "인터랙션 및 가이드:", "ja": "操作とガイド:"},
    "说明模式 (显示 [?] 悬浮说明)": {
        "en": "Help Mode (Show [?] Hover Tips)",
        "ko": "설명 모드 ([?] 호버 도움말 표시)",
        "ja": "説明モード ([?] ホバー解説を表示)",
    },
    "交互聚焦动画": {
        "en": "Focus Hover Animations",
        "ko": "포커스 호버 애니메이션",
        "ja": "フォーカスホバーアニメーション",
    },
    "界面布局": {"en": "Workspace Layout", "ko": "작업 공간 레이아웃", "ja": "ワークスペース配置"},
    "实时分析布局": {"en": "Live Analysis Layout", "ko": "실시간 분석 레이아웃", "ja": "リアルタイム解析配置"},
    "字体与大小": {"en": "Font & Size", "ko": "글꼴 및 크기", "ja": "フォントとサイズ"},
    "背景色": {"en": "Background", "ko": "배경색", "ja": "背景色"},
    "字色": {"en": "Text Color", "ko": "글자색", "ja": "文字色"},
    "强调色": {"en": "Accent Color", "ko": "강조색", "ja": "アクセント色"},
    "选色": {"en": "Pick", "ko": "선택", "ja": "選択"},
    "清除": {"en": "Clear", "ko": "지우기", "ja": "クリア"},
    "使用预设颜色": {"en": "Use preset color", "ko": "프리셋 색상 사용", "ja": "プリセット色を使用"},
    "未设置自定义背景图（仅非酸性主题可用）": {
        "en": "No custom wallpaper set (non-Acid themes only)",
        "ko": "사용자 배경 이미지 없음 (비-애시드 테마 전용)",
        "ja": "カスタム壁紙未設定 (非アシッドテーマ専用)",
    },
    "默认系统字体 (Segoe UI / 微软雅黑)": {
        "en": "Default System Font (Segoe UI / Sans)",
        "ko": "기본 시스템 글꼴 (Segoe UI / 맑은 고딕)",
        "ja": "既定システムフォント (Segoe UI / 游ゴシック)",
    },
    "A · 工作台": {"en": "A · Workbench", "ko": "A · 워크벤치", "ja": "A · ワークベンチ"},
    "B · 双栏扒谱（默认）": {"en": "B · Split Transcription (Default)", "ko": "B · 2단 채보 (기본)", "ja": "B · 2カラム耳コピ (既定)"},
    "C · 练习优先": {"en": "C · Practice First", "ko": "C · 연습 우선", "ja": "C · 練習優先"},
    "音轨、分析和历史波形从上到下排列。": {
        "en": "Stems, analysis views, and history waveform stacked top to bottom.",
        "ko": "스템, 분석 패널, 히스토리 파형이 위에서 아래로 배치됩니다.",
        "ja": "ステム・解析パネル・履歴波形を上から順に配置します。",
    },
    "左侧切换音轨，右侧查看分析，历史波形在下方。": {
        "en": "Stems on the left, analysis on the right, and 120s history waveform below.",
        "ko": "왼쪽에서 스템 전환, 오른쪽에서 분석 확인, 아래에 히스토리 파형을 표시합니다.",
        "ja": "左でステム切替、右で解析表示、下部に履歴波形を配置します。",
    },
    "历史波形置顶并放大，下方并排显示分析和音轨。": {
        "en": "Expanded history waveform on top, with analysis and stems side by side below.",
        "ko": "히스토리 파형을 상단에 확대 배치하고, 하단에 분석과 스템을 나란히 표시합니다.",
        "ja": "履歴波形を上部に拡大配置し、下部に解析とステムを並べて表示します。",
    },
    "实时监听（默认）": {"en": "Live Monitor (Default)", "ko": "실시간 모니터 (기본)", "ja": "リアルタイムモニター (既定)"},
    "液态玻璃卡片": {"en": "Liquid Glass Cards", "ko": "리퀴드 글래스 카드", "ja": "リキッドグラスカード"},
    "光学效果范围": {"en": "Optics Scope", "ko": "광학 효과 범위", "ja": "光学エフェクト範囲"},
    "仅悬浮小件（推荐）": {"en": "Floating Pills Only (Recommended)", "ko": "플로팅 위젯만 (권장)", "ja": "フローティング部品のみ (推奨)"},
    "全部面板": {"en": "All Panels", "ko": "모든 패널", "ja": "すべてのパネル"},
    "关闭光学高光": {"en": "Disable Optics", "ko": "광학 효과 끄기", "ja": "光学エフェクト無効"},
    "折射观感": {"en": "Refraction", "ko": "굴절감", "ja": "屈折感"},
    "玻璃柔化": {"en": "Softness", "ko": "유리 부드러움", "ja": "ソフトネス"},
    "边缘色散观感": {"en": "Edge Dispersion", "ko": "가장자리 색분산", "ja": "エッジ色収差"},
    "玻璃材质使用渐变模拟，不采样背景像素。": {
        "en": "Glass highlights are simulated with lightweight gradients without sampling background pixels.",
        "ko": "유리 질감은 배경 픽셀 샘플링 없이 경량 그라데이션으로 시뮬레이션됩니다.",
        "ja": "ガラス質感は背景ピクセルをサンプリングせず軽量グラデーションで描画します。",
    },
    "实时预览主界面": {"en": "Live Preview Main Window", "ko": "메인 창 실시간 미리보기", "ja": "メイン画面リアルタイムプレビュー"},
    "外观预览": {"en": "Theme Preview", "ko": "테마 미리보기", "ja": "テーマプレビュー"},
    "实时分析 · 音符 / 和弦": {"en": "Live Analysis · Notes / Chords", "ko": "실시간 분석 · 음표 / 코드", "ja": "リアルタイム解析 · 音符 / コード"},
    "恢复默认": {"en": "Restore Defaults", "ko": "기본값 복원", "ja": "初期設定に戻す"},
    "保存": {"en": "Save", "ko": "저장", "ja": "保存"},
    "🔒 酸性遥测风格已锁定标准工业字体、官方配色、玻璃高光与背景图（字号 11–20px、黑夜/白天/跟随系统、语言与布局仍可自由调节）。": {
        "en": "🔒 Acid Telemetry locks official industrial typography, palette, glass optics, and wallpaper (font size 11–20px, Light/Dark/System mode, language, help mode, animations & layouts remain adjustable).",
        "ko": "🔒 애시드 텔레메트리 테마는 표준 산업 글꼴, 공식 색상, 유리 광택 및 배경 이미지를 잠급니다(글꼴 크기 11–20px, 라이트/다크/시스템, 언어, 설명 모드 및 레이아웃은 자유 조절 가능).",
        "ja": "🔒 アシッドテレメトリでは工業標準フォント・公式配色・ガラス光沢・壁紙がロックされます（文字サイズ 11–20px・ライト/ダーク/システム・言語・説明モード・レイアウトは自由に調整可能）。",
    },
    # --- SettingsDialog ---
    "外观与布局": {"en": "Appearance & Layout", "ko": "외관 및 레이아웃", "ja": "外観とレイアウト"},
    "资源保护": {"en": "Resource Guardrails", "ko": "리소스 보호", "ja": "リソース保護"},
    "系统设置与运行环境管理": {
        "en": "System Settings & Runtime Management",
        "ko": "시스템 설정 및 실행 환경 관리",
        "ja": "システム設定と実行環境管理",
    },
    "切换工作区、黑夜/白天/跟随系统主题、语言、数据路径与开源项目反馈": {
        "en": "Configure theme mode, workspace layout, language, help mode, portable paths, and project feedback.",
        "ko": "작업 공간, 라이트/다크/시스템 테마, 언어, 설명 모드, 데이터 경로 및 프로젝트 피드백 설정",
        "ja": "ワークスペース・ライト/ダーク/システム切替・言語・説明モード・保存先・フィードバック設定",
    },
    "APPEARANCE // 当前外观、多语言与壳体配置": {
        "en": "APPEARANCE // THEME, LANGUAGE & WINDOW SHELL",
        "ko": "APPEARANCE // 현재 외관, 다국어 및 창 프레임 설정",
        "ja": "APPEARANCE // 外観・多言語・ウィンドウ構成",
    },
    "PORTABLE STORAGE // 同级目录保存位置（默认不写入 C 盘）": {
        "en": "PORTABLE STORAGE // APP-ADJACENT PATHS (NO C: DRIVE CLUTTER)",
        "ko": "PORTABLE STORAGE // 동일 폴더 저장 위치 (기본 C드라이브 미사용)",
        "ja": "PORTABLE STORAGE // 同階層ポータブル保存先 (Cドライブ既定不使用)",
    },
    "OPEN SOURCE && FEEDBACK // 开源项目地址与问题反馈": {
        "en": "OPEN SOURCE && FEEDBACK // REPOSITORY && ISSUES",
        "ko": "OPEN SOURCE && FEEDBACK // 오픈소스 저장소 및 피드백",
        "ja": "OPEN SOURCE && FEEDBACK // プロジェクトURL・フィードバック",
    },
    "GUARDRAILS // 8GB 显存与 16GB 系统内存保护阈值": {
        "en": "GUARDRAILS // 8GB VRAM && 16GB RAM SAFETY THRESHOLDS",
        "ko": "GUARDRAILS // 8GB VRAM 및 16GB RAM 보호 임계값",
        "ja": "GUARDRAILS // 8GB VRAM・16GB RAM 保護しきい値",
    },
    "CHUNKING && MODELS // 流式分块与实验模型": {
        "en": "CHUNKING && MODELS // STREAMING CHUNKS && EXPERIMENTAL MODELS",
        "ko": "CHUNKING && MODELS // 스트리밍 청크 및 실험 모델",
        "ja": "CHUNKING && MODELS // ストリーミング分割と実験モデル",
    },
    "HYBRID GPU OFFLOAD // 集显 + 独显异构协同加速（可选）": {
        "en": "HYBRID GPU OFFLOAD // iGPU + dGPU HETEROGENEOUS ACCELERATION (OPTIONAL)",
        "ko": "HYBRID GPU OFFLOAD // 내장 + 외장 GPU 이기종 가속 (선택)",
        "ja": "HYBRID GPU OFFLOAD // 内蔵＋外付けGPU 異種協調加速 (任意)",
    },
    "方案 A (异构计算):": {"en": "Plan A (Heterogeneous):", "ko": "방안 A (이기종 연산):", "ja": "プランA (異種演算):"},
    "方案 B (渲染隔离):": {"en": "Plan B (Render Isolation):", "ko": "방안 B (렌더링 격리):", "ja": "プランB (描画分離):"},
    "启用方案 A：核显 DirectML 接管轻量 2-Stem ONNX 分离": {
        "en": "Enable Plan A: DirectML iGPU for Lightweight 2-Stem ONNX Split",
        "ko": "방안 A 활성화: 내장 GPU DirectML로 경량 2-Stem ONNX 분리 처리",
        "ja": "プランA有効化: 内蔵GPU DirectML で軽量 2-Stem ONNX 分離を実行",
    },
    "启用方案 B：GUI 渲染卸载核显 + AI 子进程锁定独显 (CUDA_VISIBLE_DEVICES=0)": {
        "en": "Enable Plan B: Offload GUI to iGPU + Pin AI Worker to dGPU (CUDA_VISIBLE_DEVICES=0)",
        "ko": "방안 B 활성화: GUI 렌더링 내장 GPU 할당 + AI 워커 외장 GPU 고정 (CUDA_VISIBLE_DEVICES=0)",
        "ja": "プランB有効化: GUI描画を内蔵GPUへ逃がし AI ワーカーを dGPU 固定 (CUDA_VISIBLE_DEVICES=0)",
    },
    "Windows 图形设置": {"en": "Windows Graphics Settings", "ko": "Windows 그래픽 설정", "ja": "Windows グラフィック設定"},
    "TURNKEY BOOTSTRAP // 零配置集成、本机 PyTorch 扫描与一键修复": {
        "en": "TURNKEY BOOTSTRAP // LOCAL PYTORCH SCANNER & ONE-CLICK SETUP",
        "ko": "TURNKEY BOOTSTRAP // 로컬 PyTorch 스캔 및 원클릭 설정",
        "ja": "TURNKEY BOOTSTRAP // ローカルPyTorch検出とワンクリック構築",
    },
    "AI WORKER // 分轨运行环境 (PyTorch CUDA + ONNX)": {
        "en": "AI WORKER // SEPARATION RUNTIME (PYTORCH CUDA + ONNX)",
        "ko": "AI WORKER // 분리 실행 환경 (PyTorch CUDA + ONNX)",
        "ja": "AI WORKER // 分離実行環境 (PyTorch CUDA + ONNX)",
    },
    "MIDI WORKER // 转录运行环境 (Python 3.11 Basic Pitch CPU)": {
        "en": "MIDI WORKER // TRANSCRIPTION RUNTIME (PYTHON 3.11 BASIC PITCH CPU)",
        "ko": "MIDI WORKER // MIDI 변환 환경 (Python 3.11 Basic Pitch CPU)",
        "ja": "MIDI WORKER // 転写実行環境 (Python 3.11 Basic Pitch CPU)",
    },
    "主题与模式": {"en": "Theme & Mode", "ko": "테마 및 모드", "ja": "テーマとモード"},
    "工作区": {"en": "Workspace", "ko": "작업 공간", "ja": "ワークスペース"},
    "字体与字号": {"en": "Font & Size", "ko": "글꼴 및 크기", "ja": "フォントとサイズ"},
    "界面语言与壳体:": {"en": "Language & Frame:", "ko": "언어 및 프레임:", "ja": "言語とフレーム:"},
    "无边框圆角窗口": {"en": "Frameless Rounded Window", "ko": "프레임 없는 둥근 창", "ja": "フレームレス角丸ウィンドウ"},
    "编辑外观与字体…": {"en": "Customize Appearance & Fonts…", "ko": "외관 및 글꼴 편집…", "ja": "外観とフォントを編集…"},
    "应用目录:": {"en": "App Directory:", "ko": "앱 디렉터리:", "ja": "アプリフォルダ:"},
    "工作缓存与设置:": {"en": "Cache & Settings:", "ko": "캐시 및 설정:", "ja": "キャッシュと設定:"},
    "默认导出目录:": {"en": "Default Export Dir:", "ko": "기본 내보내기 폴더:", "ja": "既定の出力先:"},
    "打开应用目录": {"en": "Open App Folder", "ko": "앱 폴더 열기", "ja": "アプリフォルダを開く"},
    "打开导出目录": {"en": "Open Export Folder", "ko": "내보내기 폴더 열기", "ja": "出力フォルダを開く"},
    "⭐ 点个 Star / 项目主页": {"en": "⭐ Star on GitHub", "ko": "⭐ GitHub 스타 / 홈", "ja": "⭐ GitHub で Star / ホーム"},
    "反馈问题 (GitHub Issues)": {"en": "Report Issue (GitHub Issues)", "ko": "이슈 제보 (GitHub Issues)", "ja": "不具合報告 (GitHub Issues)"},
    "复制项目链接": {"en": "Copy Repo URL", "ko": "저장소 URL 복사", "ja": "リポジトリURLをコピー"},
    "已复制项目链接 ✓": {"en": "Repo URL Copied ✓", "ko": "저장소 URL 복사됨 ✓", "ja": "URLをコピーしました ✓"},
    "分轨前内存提醒": {"en": "Pre-Split RAM Warning", "ko": "분리 전 RAM 경고", "ja": "分離前 RAM 警告"},
    "拒绝新分轨的内存阈值": {"en": "Refuse New Split RAM Floor", "ko": "신규 분리 거부 RAM 하한", "ja": "新規分離拒否 RAM 下限"},
    "紧急停止的内存阈值": {"en": "E-Stop Critical RAM Floor", "ko": "긴급 정지 임계 RAM", "ja": "緊急停止 RAM しきい値"},
    "GPU 2-Stem 最低空闲显存:": {"en": "GPU 2-Stem Min Free VRAM:", "ko": "GPU 2-Stem 최소 여유 VRAM:", "ja": "GPU 2-Stem 最小空きVRAM:"},
    "GPU 4-Stem 最低空闲显存:": {"en": "GPU 4-Stem Min Free VRAM:", "ko": "GPU 4-Stem 최소 여유 VRAM:", "ja": "GPU 4-Stem 最小空きVRAM:"},
    "桌面/播放器保留最低空闲显存:": {"en": "Reserved Desktop/Player VRAM:", "ko": "데스크톱/플레이어 예약 VRAM:", "ja": "デスクトップ/再生用確保VRAM:"},
    "离线音频流式分块长度:": {"en": "Streaming Chunk Length:", "ko": "오프라인 스트리밍 청크 길이:", "ja": "ストリーミング分割長:"},
    "HTDemucs 4-Stem 模型分段:": {"en": "HTDemucs 4-Stem Segment:", "ko": "HTDemucs 4-Stem 세그먼트:", "ja": "HTDemucs 4-Stem セグメント:"},
    "高显存模型解锁:": {"en": "High-VRAM Model Unlock:", "ko": "고VRAM 모델 잠금 해제:", "ja": "高VRAMモデル解放:"},
    "允许实验性 BS-RoFormer 模型 (仅在 RTX 5060 Ti 8GB 实测峰值通过后手动启用)": {
        "en": "Allow Experimental BS-RoFormer (enable only after verifying 8GB VRAM headroom)",
        "ko": "실험적 BS-RoFormer 모델 허용 (8GB VRAM 여유 확인 후 수동 활성화)",
        "ja": "実験的 BS-RoFormer モデルを許可 (8GB VRAM 余裕を確認後に手動有効化)",
    },
    "可选：本地 cu128 wheel 目录（留空则在线安装 PyTorch cu128）": {
        "en": "Optional: Local cu128 wheel folder (leave blank to download online)",
        "ko": "선택: 로컬 cu128 wheel 폴더 (비워두면 온라인 설치)",
        "ja": "任意: ローカル cu128 wheel フォルダ (空欄ならオンライン導入)",
    },
    "自动识别 runtime\\ai 或 .venv-ai\\Scripts\\python.exe（也可扫描本机或手动指定）": {
        "en": "Auto-detects runtime\\ai or .venv-ai\\Scripts\\python.exe (or scan local / browse)",
        "ko": "runtime\\ai 또는 .venv-ai\\Scripts\\python.exe 자동 감지 (로컬 스캔/직접 지정 가능)",
        "ja": "runtime\\ai または .venv-ai\\Scripts\\python.exe を自動検出 (ローカル検出/手動指定可)",
    },
    "自动识别同级 m / runtime\\midi / .venv-midi\\Scripts\\python.exe": {
        "en": "Auto-detects adjacent m / runtime\\midi / .venv-midi\\Scripts\\python.exe",
        "ko": "동일 폴더의 m / runtime\\midi / .venv-midi\\Scripts\\python.exe 자동 감지",
        "ja": "同階層の m / runtime\\midi / .venv-midi\\Scripts\\python.exe を自動検出",
    },
    "选本地 wheel…": {"en": "Local Wheels…", "ko": "로컬 wheel…", "ja": "ローカル wheel…"},
    "扫描本机 PyTorch 环境": {"en": "Scan Local PyTorch", "ko": "로컬 PyTorch 스캔", "ja": "ローカル PyTorch 検出"},
    "一键自动配置 AI + MIDI": {"en": "One-Click Setup AI + MIDI", "ko": "AI + MIDI 원클릭 구성", "ja": "AI + MIDI 一括構築"},
    "仅自动配置 CPU MIDI": {"en": "Setup CPU MIDI Only", "ko": "CPU MIDI만 구성", "ja": "CPU MIDI のみ構築"},
    "PyTorch 官方下载页 (pytorch.org)": {"en": "PyTorch Download (pytorch.org)", "ko": "PyTorch 공식 다운로드 (pytorch.org)", "ja": "PyTorch 公式ダウンロード (pytorch.org)"},
    "CUDA 12.8 Wheel 官方镜像": {"en": "CUDA 12.8 Wheel Index", "ko": "CUDA 12.8 Wheel 공식 미러", "ja": "CUDA 12.8 Wheel 公式ミラー"},
    "Python 3.12 官方下载": {"en": "Download Python 3.12", "ko": "Python 3.12 공식 다운로드", "ja": "Python 3.12 公式ダウンロード"},
    "缺 Python 3.12/3.11 时自动用 winget 安装": {
        "en": "Auto-install missing Python 3.12/3.11 via winget",
        "ko": "Python 3.12/3.11 없을 때 winget으로 자동 설치",
        "ja": "Python 3.12/3.11 不足時に winget で自動導入",
    },
    "浏览...": {"en": "Browse...", "ko": "찾아보기...", "ja": "参照..."},
    "验证 AI 环境": {"en": "Verify AI Env", "ko": "AI 환경 검증", "ja": "AI 環境を検証"},
    "验证 MIDI 环境": {"en": "Verify MIDI Env", "ko": "MIDI 환경 검증", "ja": "MIDI 環境を検証"},
    "准备就绪：点击「扫描本机 PyTorch 环境」自动查找电脑已安装的 PyTorch；若未安装会给出官方下载地址与安装指令。": {
        "en": "Ready: Click 'Scan Local PyTorch' to auto-detect existing PyTorch installations; if missing, official download links and commands will be shown.",
        "ko": "준비 완료: '로컬 PyTorch 스캔'을 눌러 설치된 PyTorch를 자동 검색하세요. 미설치 시 공식 다운로드 주소와 명령을 안내합니다.",
        "ja": "準備完了:「ローカル PyTorch 検出」で既存のPyTorchを自動検出します。未導入時は公式URLと導入手順を案内します。",
    },
    "验证 CUDA、ONNX、Demucs 和 FFmpeg。若本机未安装 PyTorch，请访问 https://pytorch.org/get-started/locally/ 下载。": {
        "en": "Verifies CUDA, ONNX, Demucs & FFmpeg. If PyTorch is not installed locally, download it from https://pytorch.org/get-started/locally/",
        "ko": "CUDA, ONNX, Demucs 및 FFmpeg를 검증합니다. PyTorch가 없으면 https://pytorch.org/get-started/locally/ 에서 설치하세요.",
        "ja": "CUDA・ONNX・Demucs・FFmpeg を検証します。PyTorch未導入時は https://pytorch.org/get-started/locally/ から取得できます。",
    },
    "Basic Pitch 使用独立的 Python 3.11 CPU 环境。安装版内置短路径 m/ 或同级 .venv-midi 时会自动启用。": {
        "en": "Basic Pitch runs in an isolated Python 3.11 CPU environment. Auto-enabled when bundled short-path m/ or adjacent .venv-midi exists.",
        "ko": "Basic Pitch는 독립 Python 3.11 CPU 환경에서 실행됩니다. 설치판 내장 m/ 또는 .venv-midi가 있으면 자동 활성화됩니다.",
        "ja": "Basic Pitchは独立したPython 3.11 CPU環境で動作します。内蔵の短縮パス m/ または同階層 .venv-midi があれば自動有効化されます。",
    },
    # --- Settings System Table ---
    "检测项": {"en": "Check Item", "ko": "점검 항목", "ja": "診断項目"},
    "当前环境实测状态": {"en": "Detected Status", "ko": "현재 환경 실측 상태", "ja": "現在の実測状態"},
    "操作系统": {"en": "Operating System", "ko": "운영체제", "ja": "オペレーティングシステム"},
    "Windows Build / WASAPI 进程捕获": {
        "en": "Windows Build / WASAPI Process Loopback",
        "ko": "Windows 빌드 / WASAPI 프로세스 캡처",
        "ja": "Windows ビルド / WASAPI プロセスキャプチャ",
    },
    "系统 RAM (总量 / 当前可用)": {"en": "System RAM (Total / Free)", "ko": "시스템 RAM (전체 / 가용)", "ja": "システム RAM (合計 / 空き)"},
    "GPU 型号": {"en": "GPU Model", "ko": "GPU 모델", "ja": "GPU モデル"},
    "VRAM (总量 / 空闲)": {"en": "VRAM (Total / Free)", "ko": "VRAM (전체 / 여유)", "ja": "VRAM (合計 / 空き)"},
    "RTX 5060 Ti sm_120 支持 / Kernel 测试": {
        "en": "RTX 5060 Ti sm_120 Support / Kernel Test",
        "ko": "RTX 5060 Ti sm_120 지원 / 커널 테스트",
        "ja": "RTX 5060 Ti sm_120 対応 / カーネル検証",
    },
    "GPU AI 准入状态 (gpu_ai_ready)": {
        "en": "GPU AI Readiness (gpu_ai_ready)",
        "ko": "GPU AI 준비 상태 (gpu_ai_ready)",
        "ja": "GPU AI 実行可否 (gpu_ai_ready)",
    },
    # --- ChordPracticeDialog ---
    "请选择大调或小调": {"en": "Select Major or Minor Key", "ko": "장조 또는 단조 선택", "ja": "メジャー / マイナー調を選択"},
    "原曲快照参考": {"en": "Original Song Snapshot", "ko": "원곡 스냅샷 참고", "ja": "原曲スナップショット参照"},
    "练习调": {"en": "Practice Key", "ko": "연습 조성", "ja": "練習キー"},
    "速度": {"en": "Tempo", "ko": "템포", "ja": "テンポ"},
    "按稳定检测调性选中，可切换": {
        "en": "Auto-selected from stable detected key (changeable)",
        "ko": "안정적 감지 조성으로 자동 선택됨 (변경 가능)",
        "ja": "安定検出された調を自動選択済み（変更可能）",
    },
    "手动选调": {"en": "Manual key selection", "ko": "수동 조성 선택", "ja": "手動キー選択"},
    "选中上方任意进行后，可试听或导出为标准 .mid 文件。": {
        "en": "Select any progression above to audition or export as a Cubase-ready standard .mid file.",
        "ko": "위에서 진행을 선택한 뒤 미리듣기하거나 표준 .mid 파일로 내보낼 수 있습니다.",
        "ja": "上の進行を選択すると、試聴または標準 .mid ファイルとして出力できます。",
    },
    "试听进行": {"en": "Audition Progression", "ko": "진행 미리듣기", "ja": "進行を試聴"},
    "停止试听": {"en": "Stop Audition", "ko": "미리듣기 중지", "ja": "試聴を停止"},
    "导出进行 MIDI": {"en": "Export Progression MIDI", "ko": "진행 MIDI 내보내기", "ja": "進行 MIDI を出力"},
    "关闭": {"en": "Close", "ko": "닫기", "ja": "閉じる"},
    "罗马级数": {"en": "Roman Degrees", "ko": "로마 숫자 도수", "ja": "ローマ度数"},
    "和弦": {"en": "Chords", "ko": "코드", "ja": "コード"},
    "最近和弦匹配": {"en": "Recent Match", "ko": "최근 코드 일치", "ja": "直近コード一致"},
    "通用练习": {"en": "Common Practice", "ko": "일반 연습", "ja": "定番練習"},
    # --- Table headers across Mixer & Resource Tabs ---
    "开始 (s)": {"en": "Start (s)", "ko": "시작 (s)", "ja": "開始 (s)"},
    "结束 (s)": {"en": "End (s)", "ko": "종료 (s)", "ja": "終了 (s)"},
    "和弦候选": {"en": "Chord", "ko": "코드 후보", "ja": "コード候補"},
    "第二候选": {"en": "2nd Candidate", "ko": "2순위 후보", "ja": "第2候補"},
    "相关度": {"en": "Corr", "ko": "상관도", "ja": "相関度"},
    "稳定度": {"en": "Stability", "ko": "안정도", "ja": "安定度"},
    "音符": {"en": "Note", "ko": "음표", "ja": "音名"},
    "MIDI 编号": {"en": "MIDI #", "ko": "MIDI 번호", "ja": "MIDI 番号"},
    "力度": {"en": "Vel", "ko": "벨로시티", "ja": "ベロシティ"},
    "时间(UTC)": {"en": "Time (UTC)", "ko": "시간 (UTC)", "ja": "時刻 (UTC)"},
    "模型": {"en": "Model", "ko": "모델", "ja": "モデル"},
    "设备": {"en": "Device", "ko": "장치", "ja": "デバイス"},
    "输入(s)": {"en": "Input (s)", "ko": "입력 (s)", "ja": "入力 (s)"},
    "分段(s)": {"en": "Seg (s)", "ko": "세그먼트 (s)", "ja": "分割 (s)"},
    "峰值RAM(MB)": {"en": "Peak RAM (MB)", "ko": "피크 RAM (MB)", "ja": "最大RAM (MB)"},
    "峰值VRAM(MB)": {"en": "Peak VRAM (MB)", "ko": "피크 VRAM (MB)", "ja": "最大VRAM (MB)"},
    "状态": {"en": "Status", "ko": "상태", "ja": "状態"},
    # --- PlotWidget axes & remaining bilingual labels ---
    "包络点": {"en": "Envelope Samples", "ko": "엔벨로프 포인트", "ja": "エンベロープ点"},
    "频率 (Hz)": {"en": "Frequency (Hz)", "ko": "주파수 (Hz)", "ja": "周波数 (Hz)"},
    "更新帧（右侧为最新）": {
        "en": "Update Frames (Newest Right)",
        "ko": "업데이트 프레임 (오른쪽이 최신)",
        "ja": "更新フレーム（右が最新）",
    },
    "频带序号": {"en": "Band Index", "ko": "대역 인덱스", "ja": "帯域インデックス"},
    "循环范围: 全曲": {"en": "Loop Scope: Full Track", "ko": "루프 범위: 전체", "ja": "ループ範囲: 全曲"},
    "PIANO ROLL // MIDI 钢琴卷帘预览 (单击可跳转播放)": {
        "en": "PIANO ROLL // MIDI Preview (Click to Seek)",
        "ko": "PIANO ROLL // MIDI 피아노 롤 미리보기 (클릭하여 탐색)",
        "ja": "PIANO ROLL // MIDI ピアノロール表示 (クリックでシーク)",
    },
    "CHORD_PRACTICE // 练习和弦": {
        "en": "CHORD_PRACTICE",
        "ko": "CHORD_PRACTICE // 코드 연습",
        "ja": "CHORD_PRACTICE // コード練習",
    },
    "RESET // TRACK // 换歌重置": {
        "en": "RESET // TRACK",
        "ko": "RESET // TRACK // 트랙 리셋",
        "ja": "RESET // TRACK // 曲変更リセット",
    },
}

# Dynamic regex / fragment replacement rules for runtime-formatted labels and table cells.
# Each entry: (compiled_regex, {lang: replacement_str})
DYNAMIC_REGEX_RULES: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    # Audio source combo items
    (
        re.compile(r"^\[进程\]\s*"),
        {"en": "[Proc] ", "ko": "[프로세스] ", "ja": "[プロセス] "},
    ),
    (
        re.compile(r"^\[兜底\]\s*系统 WASAPI Loopback \(会混入其他应用声音\)$"),
        {
            "en": "[Fallback] System WASAPI Loopback (captures all system audio)",
            "ko": "[폴백] 시스템 WASAPI 루프백 (다른 앱 소리 포함)",
            "ja": "[フォールバック] システム WASAPI ループバック (他アプリ音混入)",
        },
    ),
    (
        re.compile(r"^\[测试信号\]\s*Synthetic Switching \(440Hz/静音/659Hz\)$"),
        {
            "en": "[Test Signal] Synthetic Switching (440Hz / Silence / 659Hz)",
            "ko": "[테스트 신호] Synthetic Switching (440Hz / 무음 / 659Hz)",
            "ja": "[テスト信号] Synthetic Switching (440Hz / 無音 / 659Hz)",
        },
    ),
    # Capo transpose items
    (
        re.compile(r"^Capo (\d+) \((-\d+) 半音指型\)$"),
        {"en": r"Capo \1 (\2 st shape)", "ko": r"Capo \1 (\2 반음 운지)", "ja": r"Capo \1 (\2 半音フォーム)"},
    ),
    # SpinBox prefixes & values
    (
        re.compile(r"^倒退\s+"),
        {"en": "From -", "ko": "시작 -", "ja": "開始 -"},
    ),
    (
        re.compile(r"^至倒退\s+"),
        {"en": "To -", "ko": "끝 -", "ja": "終了 -"},
    ),
    # Major / Minor key labels
    (
        re.compile(r"^([A-G][#b]?)\s*大调$"),
        {"en": r"\1 Major", "ko": r"\1 장조", "ja": r"\1 メジャー"},
    ),
    (
        re.compile(r"^([A-G][#b]?)\s*小调$"),
        {"en": r"\1 Minor", "ko": r"\1 단조", "ja": r"\1 マイナー"},
    ),
    # Matched steps in ChordPracticeDialog
    (
        re.compile(r"^(\d+)\s*步$"),
        {"en": r"\1 steps", "ko": r"\1스텝", "ja": r"\1ステップ"},
    ),
    # Stability / correlation / relation fragments
    (
        re.compile(r"\|\s*相关\s*"),
        {"en": "| Corr ", "ko": "| 상관 ", "ja": "| 相関 "},
    ),
    (
        re.compile(r"\|\s*差\s*"),
        {"en": "| Margin ", "ko": "| 차이 ", "ja": "| 差 "},
    ),
    (
        re.compile(r"自相关峰:\s*"),
        {"en": "Autocorr Peak: ", "ko": "자기상관 피크: ", "ja": "自己相関ピーク: "},
    ),
    (
        re.compile(r"\|\s*关系说明:\s*等待音频"),
        {"en": "| Relation: Waiting for audio", "ko": "| 관계: 오디오 대기 중", "ja": "| 関係: 音声待機中"},
    ),
    (
        re.compile(r"\|\s*关系说明:\s*"),
        {"en": "| Relation: ", "ko": "| 관계: ", "ja": "| 関係: "},
    ),
    (
        re.compile(r"平行大小调"),
        {"en": "Relative Major/Minor", "ko": "나란한조", "ja": "平行調"},
    ),
    (
        re.compile(r"待启动按进程捕获（也可随时手动点击「换歌重置」）"),
        {
            "en": "Waiting for Process Capture (or click Reset Track manually)",
            "ko": "프로세스 캡처 대기 중 (수동으로 '트랙 리셋' 클릭 가능)",
            "ja": "プロセスキャプチャ待機中（手動で「曲変更リセット」も可能）",
        },
    ),
    # Recent progression header with fullwidth or ASCII parentheses
    (
        re.compile(r"^最近和弦进行\s*[（(]最多\s*12\s*步[)）]:"),
        {
            "en": "Recent Progression (<=12 steps):",
            "ko": "최근 코드 진행 (최대 12스텝):",
            "ja": "直近コード進行 (最大12ステップ):",
        },
    ),
    # ChordPracticeDialog dynamic labels
    (
        re.compile(r"原曲检测调性:\s*(.+?)（稳定度:\s*(.+?)）"),
        {
            "en": r"Detected Key: \1 (Stability: \2)",
            "ko": r"원곡 감지 조성: \1 (안정도: \2)",
            "ja": r"検出キー: \1（安定度: \2）",
        },
    ),
    (
        re.compile(r"检测速度:\s*"),
        {
            "en": "Detected Tempo: ",
            "ko": "감지 템포: ",
            "ja": "検出テンポ: ",
        },
    ),
    (
        re.compile(r"^最近识别实音:\s*"),
        {"en": "Recent Detected Chords: ", "ko": "최근 감지 실음: ", "ja": "直近検出コード: "},
    ),
    (
        re.compile(r"^试听与 MIDI 口径：(.+?)（实音，未移调）\s*·\s*([0-9.]+)\s*BPM\s*·\s*每和弦\s*(\d+)\s*拍$"),
        {
            "en": r"Audition & MIDI: \1 (Concert pitch) · \2 BPM · \3 beats/chord",
            "ko": r"미리듣기 & MIDI: \1 (실음, 이조 없음) · \2 BPM · 코드당 \3박",
            "ja": r"試聴＆MIDI仕様: \1（実音・移調なし）· \2 BPM · 各コード \3拍",
        },
    ),
    (
        re.compile(r"^试听与 MIDI 口径："),
        {"en": "Audition & MIDI: ", "ko": "미리듣기 & MIDI: ", "ja": "試聴＆MIDI仕様: "},
    ),
    # Settings dynamic summaries & tables
    (
        re.compile(r"^工业标准字体 \(已锁定\)\s*·\s*(.+)$"),
        {"en": r"Industrial Standard Font (Locked) · \1", "ko": r"산업 표준 글꼴 (잠금) · \1", "ja": r"工業標準フォント (ロック中) · \1"},
    ),
    (
        re.compile(r"^系统默认\s*·\s*(.+)$"),
        {"en": r"System Default · \1", "ko": r"시스템 기본 · \1", "ja": r"システム既定 · \1"},
    ),
    *[
        rule
        for _p_zh, _p_tr in (
            ("酸性遥测", {"en": "Acid Telemetry", "ko": "애시드 텔레메트리", "ja": "アシッドテレメトリ"}),
            ("经典", {"en": "Classic", "ko": "클래식", "ja": "クラシック"}),
            ("Lenso", {"en": "Lenso", "ko": "Lenso", "ja": "Lenso"}),
            ("石墨靛紫", {"en": "Graphite", "ko": "그래파이트", "ja": "グラファイト"}),
            ("暖砂琥珀", {"en": "Warm Sand", "ko": "웜 샌드", "ja": "ウォームサンド"}),
        )
        for _m_zh, _m_tr in (
            ("白天", {"en": "Light", "ko": "라이트", "ja": "ライト"}),
            ("黑夜", {"en": "Dark", "ko": "다크", "ja": "ダーク"}),
            ("跟随系统", {"en": "System", "ko": "시스템", "ja": "システム"}),
        )
        for rule in (
            (
                re.compile(rf"^{re.escape(_p_zh)}\s*·\s*{_m_zh}\s*·\s*简体中文\s*\(ZH\)$"),
                {
                    "en": f"{_p_tr['en']} · {_m_tr['en']} · Simplified Chinese (ZH)",
                    "ko": f"{_p_tr['ko']} · {_m_tr['ko']} · 중국어 간체 (ZH)",
                    "ja": f"{_p_tr['ja']} · {_m_tr['ja']} · 簡体字中国語 (ZH)",
                },
            ),
            (
                re.compile(rf"^{re.escape(_p_zh)}\s*·\s*{_m_zh}\s*·\s*日本語\s*\(JA\)$"),
                {
                    "en": f"{_p_tr['en']} · {_m_tr['en']} · Japanese (JA)",
                    "ko": f"{_p_tr['ko']} · {_m_tr['ko']} · 일본어 (JA)",
                    "ja": f"{_p_tr['ja']} · {_m_tr['ja']} · 日本語 (JA)",
                },
            ),
            (
                re.compile(rf"^{re.escape(_p_zh)}\s*·\s*{_m_zh}\s*·\s*한국어\s*\(KO\)$"),
                {
                    "en": f"{_p_tr['en']} · {_m_tr['en']} · Korean (KO)",
                    "ko": f"{_p_tr['ko']} · {_m_tr['ko']} · 한국어 (KO)",
                    "ja": f"{_p_tr['ja']} · {_m_tr['ja']} · 韓国語 (KO)",
                },
            ),
            (
                re.compile(rf"^{re.escape(_p_zh)}\s*·\s*{_m_zh}\s*·\s*(.+)$"),
                {
                    "en": rf"{_p_tr['en']} · {_m_tr['en']} · \1",
                    "ko": rf"{_p_tr['ko']} · {_m_tr['ko']} · \1",
                    "ja": rf"{_p_tr['ja']} · {_m_tr['ja']} · \1",
                },
            ),
        )
    ],
    (
        re.compile(r"如果 ListenScope 对你的扒谱、贝斯分析或和弦练习有帮助，欢迎前往 GitHub 点个 ⭐ Star 支持！\n• 项目仓库: (.+?)\s+\|\s+问题反馈: (.+?)\s+（暂为私有占位，转公开后可直提 Issue）"),
        {
            "en": r"If ListenScope helps your transcription, bass analysis, or chord practice, please consider giving it a ⭐ Star on GitHub!\n• Repository: \1  |  Issues: \2 (currently private placeholder; opens directly once public)",
            "ko": r"ListenScope가 채보, 베이스 분석, 코드 연습에 도움이 되었다면 GitHub에서 ⭐ Star를 눌러 응원해 주세요!\n• 저장소: \1  |  이슈 제보: \2 (현재 비공개 자리표시자이며 공개 전환 시 바로 연결)",
            "ja": r"ListenScopeが耳コピ・ベース解析・コード練習に役立ったら、GitHubで⭐ Starをいただけると嬉しいです！\n• リポジトリ: \1  |  不具合報告: \2（現在はプライベート用プレースホルダー、公開後に直通）",
        },
    ),
    (
        re.compile(r"Loop Scope:\s*全曲$"),
        {"en": "Loop Scope: Full Track", "ko": "루프 범위: 전체", "ja": "ループ範囲: 全曲"},
    ),
    (
        re.compile(r"同主音调式混合倾向\s*\((.+?)\)"),
        {
            "en": r"Parallel Mode Mixture (\1)",
            "ko": r"동주음 선법 혼합 경향 (\1)",
            "ja": r"同主音モード混合傾向 (\1)",
        },
    ),
    (
        re.compile(r"关系大小调接近\s*\((.+?)\)"),
        {
            "en": r"Relative Major/Minor Close (\1)",
            "ko": r"관계 장단조 근접 (\1)",
            "ja": r"平行調近接 (\1)",
        },
    ),
    (
        re.compile(r"调性中心稳定"),
        {"en": "Stable Tonal Center", "ko": "조성 중심 안정", "ja": "調性中心安定"},
    ),
    (
        re.compile(r"调性证据不足或为无调性/打击乐段落"),
        {
            "en": "Insufficient tonal evidence or percussive passage",
            "ko": "조성 근거 부족 또는 타악 구간",
            "ja": "調性根拠不足または打楽器区間",
        },
    ),
    (
        re.compile(r"疑似转调:\s*(.+)"),
        {"en": r"Modulation Hint: \1", "ko": r"전조 의심: \1", "ja": r"転調の疑い: \1"},
    ),
    (
        re.compile(r"当前运行合成测试信号源（非 Windows 真机 WASAPI 捕获）。"),
        {
            "en": "Running synthetic test signal source (not live Windows WASAPI capture).",
            "ko": "합성 테스트 신호원 실행 중 (Windows 실기 WASAPI 캡처 아님).",
            "ja": "合成テスト信号源を実行中（Windows実機WASAPIキャプチャではありません）。",
        },
    ),
    (
        re.compile(r"已降级为安全 CPU 模式。"),
        {"en": "Safely fell back to CPU mode.", "ko": "안전한 CPU 모드로 전환되었습니다.", "ja": "安全なCPUモードへフォールバックしました。"},
    ),
    (
        re.compile(r"自动扫描同级 runtime/ai、短路径 m、\.venv-ai/\.venv-midi 及本机 Conda / 系统 Python 中的 PyTorch（FFmpeg 已就绪）。"),
        {
            "en": "Auto-scans adjacent runtime/ai, short-path m, .venv-ai/.venv-midi, and local Conda / system Python for PyTorch (FFmpeg ready).",
            "ko": "동일 폴더의 runtime/ai, 단축 경로 m, .venv-ai/.venv-midi 및 로컬 Conda / 시스템 Python의 PyTorch를 자동 스캔합니다 (FFmpeg 준비됨).",
            "ja": "同階層の runtime/ai・短縮パス m・.venv-ai/.venv-midi およびローカル Conda / システム Python の PyTorch を自動スキャンします（FFmpeg準備完了）。",
        },
    ),
    (
        re.compile(r"自动扫描同级 runtime/ai、短路径 m、\.venv-ai/\.venv-midi 及本机 Conda / 系统 Python 中的 PyTorch（FFmpeg 未发现 \(WAV 可直接分析\)）。"),
        {
            "en": "Auto-scans adjacent runtime/ai, short-path m, .venv-ai/.venv-midi, and local Conda / system Python for PyTorch (FFmpeg not found; WAV supported natively).",
            "ko": "동일 폴더의 runtime/ai, m, .venv-ai/.venv-midi 및 로컬 Python의 PyTorch를 자동 스캔합니다 (FFmpeg 미감지; WAV 직접 분석 가능).",
            "ja": "同階層の runtime/ai・m・.venv-ai/.venv-midi およびローカル Python の PyTorch を自動スキャンします（FFmpeg未検出・WAVは直接解析可）。",
        },
    ),
    (
        re.compile(r"目标真机基线规格: Windows 10/11 \(Build >= 20348\) \| GPU: NVIDIA GeForce RTX 5060 Ti \| 显存: 8GB VRAM \(非 16GB\) \| 系统内存: 16GB RAM"),
        {
            "en": "Target Hardware Baseline: Windows 10/11 (Build >= 20348) | GPU: NVIDIA GeForce RTX 5060 Ti | VRAM: 8GB (not 16GB) | System RAM: 16GB",
            "ko": "타깃 하드웨어 기준: Windows 10/11 (Build >= 20348) | GPU: NVIDIA GeForce RTX 5060 Ti | VRAM: 8GB (16GB 아님) | RAM: 16GB",
            "ja": "ターゲット実機基準: Windows 10/11 (Build >= 20348) | GPU: NVIDIA GeForce RTX 5060 Ti | VRAM: 8GB (16GB非搭載) | RAM: 16GB",
        },
    ),
    (
        re.compile(r"\[WARN\] 当前在 Linux 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。"),
        {
            "en": "[WARN] Running on Linux: WASAPI Process Loopback and RTX 5060 Ti CUDA are unverified on live Windows hardware.",
            "ko": "[WARN] 현재 Linux에서 실행 중: WASAPI 프로세스 캡처 및 RTX 5060 Ti CUDA는 Windows 실기에서 검증되지 않았습니다.",
            "ja": "[WARN] Linux実行中: WASAPIプロセスキャプチャおよび RTX 5060 Ti CUDA は Windows実機未検証です。",
        },
    ),
    (
        re.compile(r"未检测到 NVIDIA GPU"),
        {"en": "No NVIDIA GPU detected", "ko": "NVIDIA GPU 미감지", "ja": "NVIDIA GPU 未検出"},
    ),
    (
        re.compile(r"N/A \(目标真机为 8GB VRAM\)"),
        {"en": "N/A (Target PC: 8GB VRAM)", "ko": "N/A (타깃 PC: 8GB VRAM)", "ja": "N/A (ターゲット実機: 8GB VRAM)"},
    ),
    (
        re.compile(r"N/A / 不可用 / 未在 Windows 真机验证"),
        {"en": "N/A / Unavailable / Unverified on Windows", "ko": "N/A / 사용 불가 / Windows 실기 미검증", "ja": "N/A / 利用不可 / Windows実機未検証"},
    ),
    (
        re.compile(r"未检测到 / 不可用"),
        {"en": "Not Detected / Unavailable", "ko": "미감지 / 사용 불가", "ja": "未検出 / 利用不可"},
    ),
    (
        re.compile(r"不可用 / N/A"),
        {"en": "Unavailable / N/A", "ko": "사용 불가 / N/A", "ja": "利用不可 / N/A"},
    ),
    (
        re.compile(r"未安装 / 不存在"),
        {"en": "Not Installed / Missing", "ko": "미설치 / 없음", "ja": "未導入 / なし"},
    ),
    (
        re.compile(r"未检测到 \(可点击「扫描本机 PyTorch」或前往 (.+?) 下载\)"),
        {
            "en": r"Not Detected (click 'Scan Local PyTorch' or download at \1)",
            "ko": r"미감지 ('로컬 PyTorch 스캔' 클릭 또는 \1 에서 다운로드)",
            "ja": r"未検出（「ローカル PyTorch 検出」または \1 からダウンロード）",
        },
    ),
    (
        re.compile(r"未在本机扫描到已安装 PyTorch 的 Python 环境。"),
        {
            "en": "No local Python environment with PyTorch was detected on this machine.",
            "ko": "이 PC에서 PyTorch가 설치된 Python 환경을 찾지 못했습니다.",
            "ja": "このPC上で PyTorch が導入された Python 環境は検出されませんでした。",
        },
    ),
    (
        re.compile(r"• Python 3\.12 \(64位\) 官方下载:"),
        {
            "en": "• Python 3.12 (64-bit) Official Download:",
            "ko": "• Python 3.12 (64비트) 공식 다운로드:",
            "ja": "• Python 3.12 (64bit) 公式ダウンロード:",
        },
    ),
    (
        re.compile(r"• PyTorch 官方下载指引:"),
        {
            "en": "• PyTorch Official Download Guide:",
            "ko": "• PyTorch 공식 다운로드 안내:",
            "ja": "• PyTorch 公式ダウンロード案内:",
        },
    ),
    (
        re.compile(r"• RTX 5060 Ti \(sm_120\) CUDA 12\.8 镜像源:"),
        {
            "en": "• RTX 5060 Ti (sm_120) CUDA 12.8 Index:",
            "ko": "• RTX 5060 Ti (sm_120) CUDA 12.8 인덱스:",
            "ja": "• RTX 5060 Ti (sm_120) CUDA 12.8 インデックス:",
        },
    ),
    (
        re.compile(r"• 推荐安装命令:"),
        {
            "en": "• Recommended Install Command:",
            "ko": "• 권장 설치 명령:",
            "ja": "• 推奨インストールコマンド:",
        },
    ),
    (
        re.compile(r"也可直接点击上方「一键自动配置 AI \+ MIDI」由软件自动在同级目录下载并配置。"),
        {
            "en": "Or click 'One-Click AI + MIDI Setup' above to download and configure it automatically beside the app.",
            "ko": "또는 상단의 '원클릭 AI + MIDI 설정'을 클릭하면 앱과 같은 폴더에 자동으로 다운로드 및 구성됩니다.",
            "ja": "または上部の「AI + MIDI 一括構築」をクリックすると、アプリ同階層へ自動ダウンロード・構成されます。",
        },
    ),
    (
        re.compile(r"（未就绪）|\(未就绪\)"),
        {"en": " (Not Ready)", "ko": " (미준비)", "ja": " (未準備)"},
    ),
    (
        re.compile(r"（已就绪）|\(已就绪\)"),
        {"en": " (Ready)", "ko": " (준비됨)", "ja": " (準備完了)"},
    ),
    (
        re.compile(r"\[WARN\] GPU AI 暂未就绪：([^。]+)。请点击下方按钮前往「AI 与 MIDI 环境」页扫描本机 PyTorch 或一键自动配置。"),
        {
            "en": r"[WARN] GPU AI is not ready: \1. Click below to open AI & MIDI Setup to scan local PyTorch or run One-Click Setup.",
            "ko": r"[WARN] GPU AI가 아직 준비되지 않음: \1. 아래 버튼을 눌러 'AI & MIDI 환경'에서 PyTorch를 스캔하거나 원클릭 구성을 실행하세요.",
            "ja": r"[WARN] GPU AI は未準備です: \1。下のボタンから「AI・MIDI環境」へ進み、検出または一括構築を実行してください。",
        },
    ),
    (
        re.compile(r"尚未检测到可用的 PyTorch GPU 环境"),
        {
            "en": "No usable PyTorch GPU environment detected yet",
            "ko": "사용 가능한 PyTorch GPU 환경이 아직 감지되지 않았습니다",
            "ja": "利用可能な PyTorch GPU 環境がまだ検出されていません",
        },
    ),
    (
        re.compile(r"\[BUSY\] 正在执行一键环境初始化（切换页面或关闭设置窗口不会中断下载）\.\.\."),
        {
            "en": "[BUSY] Running turnkey environment setup (switching pages or closing Settings will not interrupt downloads)...",
            "ko": "[BUSY] 원클릭 환경 구성을 실행 중입니다 (페이지를 이동하거나 설정 창을 닫아도 다운로드가 유지됩니다)...",
            "ja": "[BUSY] 環境一括構築を実行中（タブ切替や設定画面を閉じてもダウンロードは継続します）...",
        },
    ),
    (
        re.compile(r"\[OK\] 环境初始化已完成并已自动写入配置！正在刷新验证环境；若刚通过 winget 新装 Python 或硬件状态未即时更新，可点击「立即重启应用」快速生效。"),
        {
            "en": "[OK] Environment initialized & saved automatically! Refreshing validation; click 'Restart ListenScope Now' if newly installed Python paths need a reload.",
            "ko": "[OK] 환경 초기화 및 설정 자동 저장 완료! 검증을 새로고침하는 중이며 필요 시 '지금 ListenScope 다시 시작'을 누르세요.",
            "ja": "[OK] 環境構築と設定保存が完了しました！検証を再確認中です。必要に応じ「今すぐ再起動」を押してください。",
        },
    ),
    (
        re.compile(r"\[WARN\] 已取消环境初始化，你可以随时重新开始。"),
        {
            "en": "[WARN] Setup canceled. You can restart anytime.",
            "ko": "[WARN] 환경 설치가 취소되었습니다. 언제든 다시 시작할 수 있습니다.",
            "ja": "[WARN] セットアップを中止しました。いつでも再開できます。",
        },
    ),
    (
        re.compile(r"源: "),
        {
            "en": "Mirror: ",
            "ko": "미러: ",
            "ja": "ミラー: ",
        },
    ),
    (
        re.compile(r"正在启动独立环境初始化流程\.\.\."),
        {
            "en": "Starting isolated runtime bootstrap...",
            "ko": "독립 런타임 환경 구성을 시작하는 중...",
            "ja": "独立ランタイムの初期化を起動中...",
        },
    ),
    (
        re.compile(r"\[ERR\] 初始化失败 \(exit=(\d+)\):"),
        {
            "en": r"[ERR] Setup failed (exit=\1):",
            "ko": r"[ERR] 초기화 실패 (exit=\1):",
            "ja": r"[ERR] 初期化失敗 (exit=\1):",
        },
    ),
    (
        re.compile(r"检测到 Python ([^\s]+)\s*无法匹配"),
        {
            "en": r"Detected Python \1 mismatch",
            "ko": r"감지된 Python \1 버전 불일치",
            "ja": r"検出された Python \1 が不一致",
        },
    ),
    (
        re.compile(r"(^|\|\s*)下载\s+"),
        {
            "en": r"\1Downloading ",
            "ko": r"\1다운로드: ",
            "ja": r"\1ダウンロード: ",
        },
    ),
    (
        re.compile(r"(^|\|\s*)连接\s+"),
        {
            "en": r"\1Connecting ",
            "ko": r"\1연결: ",
            "ja": r"\1接続: ",
        },
    ),
)

# Full 4-language translations for all HelpBadge(title, explanation) items across the app.
HELP_TRANSLATIONS: dict[str, dict[str, tuple[str, str]]] = {
    "明暗主题与跟随系统": {
        "en": (
            "Light / Dark / System Theme Mode",
            "Light mode uses the crisp high-contrast Clinical Light workbench; Dark mode switches to low-glare dark telemetry; Follow System syncs automatically with Windows Light/Dark mode.",
        ),
        "ko": (
            "라이트 / 다크 / 시스템 테마 모드",
            "'라이트'는 고대비 클리니컬 화이트 워크벤치를, '다크'는 눈부심이 적은 다크 테마를 적용합니다. '시스템 설정 따름'은 Windows 다크/라이트 모드와 자동 동기화됩니다.",
        ),
        "ja": (
            "ライト / ダーク / システム連動モード",
            "「ライト」は高コントラストなクリニカル白基調、「ダーク」は低グレア暗所モードに切り替えます。「システムに従う」はWindowsの明暗設定に自動同期します。",
        ),
    },
    "多语言与无边框圆角壳体": {
        "en": (
            "4-Language UI & Frameless Rounded Shell",
            "Switch live between Chinese, English, Korean, and Japanese (built-in English telemetry codes stay fixed; English mode omits duplicate labels). Frameless mode replaces the thick OS border with smooth rounded corners.",
        ),
        "ko": (
            "4개 언어 및 프레임 없는 둥근 창",
            "중국어, English, 한국어, 일본어 실시간 전환을 지원합니다(고정 영문 코드는 유지되며 English 모드에서는 중복 표기 없음). 프레임 없는 둥근 창은 투박한 기본 테두리를 제거합니다.",
        ),
        "ja": (
            "4言語切替＆フレームレス角丸ウィンドウ",
            "中国語・English・韓国語・日本語をリアルタイム切替（固定英語コードは保持、Englishモードでは重複なし）。フレームレス角丸で標準の太い枠を省きスマートに表示します。",
        ),
    },
    "多语言与无边框圆角窗口": {
        "en": (
            "4-Language UI & Frameless Rounded Window",
            "• Supports Chinese, English, Korean, and Japanese live switching without duplicate labels in English.\n• Frameless rounded window removes thick OS chrome, auto-fits screen resolution, and centers cleanly on launch.",
        ),
        "ko": (
            "4개 언어 및 프레임 없는 둥근 창",
            "• 중국어, English, 한국어, 일본어 실시간 전환 지원(English 모드 중복 없음).\n• 프레임 없는 둥근 창으로 기본 시스템 테두리를 제거하고 화면 해상도에 맞춰 자동 중앙 배치합니다.",
        ),
        "ja": (
            "4言語切替＆フレームレス角丸ウィンドウ",
            "• 中国語・English・韓国語・日本語にリアルタイム対応（Englishモードでは英語重複なし）。\n• OS標準の太い枠をなくし、画面解像度に合わせて自動で中央配置します。",
        ),
    },
    "说明模式与交互聚焦动画": {
        "en": (
            "Help Mode & Focus Hover Animations",
            "• Help Mode: Shows [?] badges beside controls; hover for instant explanations. Turn off once familiar for a cleaner UI.\n• Focus Hover Animations: Lightweight GPU-free hover/focus highlight animations on buttons, selectors, and badges. Can be disabled anytime.",
        ),
        "ko": (
            "설명 모드 및 포커스 호버 애니메이션",
            "• 설명 모드: 각 기능 옆에 [?] 배지를 표시하며 마우스를 올리면 즉시 설명이 뜹니다. 익숙해지면 꺼서 더 깔끔하게 쓸 수 있습니다.\n• 포커스 호버 애니메이션: 버튼과 옵션에 가벼운 포커스 하이라이트 애니메이션을 적용합니다(VRAM 소모 없음).",
        ),
        "ja": (
            "説明モード＆フォーカスホバーアニメーション",
            "• 説明モード: 各機能横に [?] バッジを表示し、マウスを乗せるだけで即時解説します。慣れたらオフにしてスッキリ表示できます。\n• フォーカスホバーアニメーション: ボタンや項目に軽量なホバー強調アニメを付与します（VRAM消費ゼロ）。",
        ),
    },
    "系统字体扫描与字号": {
        "en": (
            "OS Font Scanner & Font Size",
            "Acid Telemetry locks the industrial font stack to preserve tight visual rhythm, while font size (11–20 px) remains adjustable. Switch to any non-Acid theme to pick any installed OS font.",
        ),
        "ko": (
            "시스템 글꼴 스캔 및 글꼴 크기",
            "애시드 텔레메트리 테마에서는 정렬과 대비를 유지하기 위해 표준 글꼴이 잠겨 있으나 글꼴 크기(11–20px)는 자유롭게 조절할 수 있습니다. 다른 테마에서는 설치된 모든 글꼴을 선택할 수 있습니다.",
        ),
        "ja": (
            "システムフォント検出＆文字サイズ",
            "アシッドテレメトリでは精密なレイアウト維持のためフォント種別がロックされますが、文字サイズ(11–20px)は自由に調整可能です。他テーマではPC内フォントを自由に選べます。",
        ),
    },
    "自定义背景壁纸（非酸性主题专享）": {
        "en": (
            "Custom Background Wallpaper (Non-Acid Themes Only)",
            "In Classic, Lenso, Graphite, and Warm Sand themes, upload any PNG/JPG/WebP image as the window backdrop with an automatic readability scrim. Disabled under Acid Telemetry to preserve graphic realism contrast.",
        ),
        "ko": (
            "사용자 배경 이미지 (비-애시드 테마 전용)",
            "Classic, Lenso, 그래파이트, 웜 샌드 테마에서는 PNG/JPG/WebP 이미지를 배경으로 업로드할 수 있으며 가독성 보호 오버레이가 자동 적용됩니다. 애시드 테마에서는 고대비 유지 차원에서 비활성화됩니다.",
        ),
        "ja": (
            "カスタム壁紙（非アシッドテーマ専用）",
            "Classic / Lenso / グラファイト / ウォームサンド テーマでは PNG/JPG/WebP 画像を背景に設定でき、視認性保護マスクが自動適用されます。アシッドテーマではコントラスト維持のため無効化されます。",
        ),
    },
    "按进程捕获说明": {
        "en": (
            "Per-Process Audio Capture (WASAPI)",
            "Select the music player process (e.g. Spotify.exe, QQMusic.exe) to capture only that app without re-recording ListenScope's metronome or mixer output. Fall back to System Loopback if Windows Build < 20348.",
        ),
        "ko": (
            "프로세스별 오디오 캡처 (WASAPI)",
            "음악 재생기 프로세스(예: Spotify.exe)를 선택하면 해당 앱 소리만 깔끔하게 캡처하여 메트로놈이나 믹서 출력이 다시 녹음되지 않습니다. Windows Build < 20348이면 시스템 루프백을 사용하세요.",
        ),
        "ja": (
            "プロセス別音声キャプチャ (WASAPI)",
            "音楽再生アプリ（例: Spotify.exe等）を指定するとそのアプリ音のみを録音でき、メトロノームやミキサー出力の再録音を防止できます。Build < 20348ではシステムループバックをご利用ください。",
        ),
    },
    "120 秒历史缓冲与 A/B 选区用法": {
        "en": (
            "120s Ring Buffer & A/B Loop Excerpts",
            "• Fixed ~46MB memory ring buffer always holds the latest 120 seconds of audio without growing.\n• Hear a phrase you want to practice? Click Last 10s/30s/60s or drag the A/B handles on the waveform below to loop, slow down, or send to AI stem separation.",
        ),
        "ko": (
            "120초 순환 버퍼 및 A/B 구간 사용법",
            "• 고정 약 46MB 메모리로 최근 120초 오디오를 계속 보관하며 메모리가 무한 증가하지 않습니다.\n• 연습하고 싶은 구간이 나오면 '최근 10s/30s/60s'를 누르거나 아래 파형에서 A/B 핸들을 드래그해 반복 재생하거나 AI 스템 분리를 실행하세요.",
        ),
        "ja": (
            "120秒リングバッファ＆A/B区間ループ",
            "• 固定約46MBのメモリで直近120秒の音声を常に保持し、メモリが増え続けません。\n• 練習したいフレーズが流れたら「直近10s/30s/60s」を押すか波形上でA/B区間をドラッグし、ループ再生・減速・AI分離へ送れます。",
        ),
    },
    "贴近零点微调与不变调变速": {
        "en": (
            "Zero-Cross Snap & Pitch-Preserving Time-Stretch",
            "• Zero-Cross: Click after stopping playback to snap A/B loop edges to the nearest zero-crossing within ±5ms, eliminating loop boundary clicks.\n• Speed (0.5x–1.25x): Pure-CPU WSOLA time-stretching slows down fast passages without shifting pitch.",
        ),
        "ko": (
            "제로크로스 스냅 및 음고유지 배속",
            "• 제로크로스 스냅: 재생 정지 후 클릭하면 A/B 경계 ±5ms 내에서 0에 가장 가까운 샘플로 맞춰 루프 끝단 팝 노이즈를 제거합니다.\n• 음고유지 배속(0.5x–1.25x): 순수 CPU WSOLA 알고리즘으로 음정 변화 없이 속도를 조절합니다.",
        ),
        "ja": (
            "ゼロクロス補正＆ピッチ維持倍速",
            "• ゼロクロス補正: 停止後に押すとA/B端の±5ms内で最も0に近いサンプル点へ吸着し、ループ境界のプチノイズを防ぎます。\n• ピッチ維持倍速(0.5x–1.25x): 純CPU WSOLA方式で音程を変えずに再生速度を変えられます。",
        ),
    },
    "A/B 实时书签说明": {
        "en": (
            "A/B Live Bookmarks",
            "Saved bookmarks anchor to absolute sample timestamps: even as music keeps playing and the 120s buffer scrolls forward, clicking Jump tracks the exact musical phrase until it leaves the 120s window.",
        ),
        "ko": (
            "A/B 실시간 북마크 안내",
            "저장된 북마크는 절대 샘플 타임스탬프에 고정됩니다. 음악이 계속 재생되어 버퍼가 앞으로 흘러가도 '북마크 이동'을 누르면 120초 창을 벗어나기 전까지 해당 악절을 정확히 추적합니다.",
        ),
        "ja": (
            "A/B リアルタイムブックマーク",
            "保存したブックマークは絶対サンプル時刻に紐付きます。音楽が流れ続けてバッファが進んでも、120秒窓から押し出されるまで「ジャンプ」で正確なフレーズへ戻れます。",
        ),
    },
    "8GB 显存防护与分轨模型": {
        "en": (
            "8GB VRAM Guardrail & Separation Models",
            "All AI stem separation runs in an isolated subprocess with 6s streaming chunks and automatic cache release. If RTX 5060 Ti (8GB VRAM) or 16GB RAM approaches safety limits, jobs are safely halted while keeping audio analysis alive.",
        ),
        "ko": (
            "8GB VRAM 보호 및 스템 분리 모델",
            "모든 AI 스템 분리는 독립 하위 프로세스에서 6초 스트리밍 청크로 실행되며 작업 후 메모리를 즉시 해제합니다. 8GB VRAM 또는 16GB RAM 임계값에 근접하면 안전하게 차단/중지합니다.",
        ),
        "ja": (
            "8GB VRAM 保護＆分離モデル",
            "AI分離は独立サブプロセスで6秒チャンク逐次処理し、終了時にメモリを完全解放します。8GB VRAMや16GB RAMの保護閾値に近づくと安全に停止し、リアルタイム解析を維持します。",
        ),
    },
    "实验性近实时二轨分离说明": {
        "en": (
            "Experimental Near-Realtime 2-Stem Separation",
            "• Streams sliding windows through a lightweight MDX 2-Stem model for live Vocal/Instrumental mixing.\n• Always use Per-Process Capture so System Loopback will not feed the separated output back into the input.",
        ),
        "ko": (
            "실험적 준실시간 2-Stem 분리 안내",
            "• 슬라이딩 윈도우로 경량 MDX 2-Stem 모델을 실행해 실시간 보컬/반주 믹싱을 제공합니다.\n• 시스템 루프백은 출력이 다시 입력으로 되먹임되므로 반드시 프로세스별 캡처를 사용하세요.",
        ),
        "ja": (
            "実験的 準リアルタイム2ステム分離",
            "• スライディング窓で軽量MDX 2-Stemモデルを動かし、ボーカル/伴奏をリアルタイムミックスします。\n• 出力の再録音を避けるため、必ず「プロセス別キャプチャ」を選択してください。",
        ),
    },
    "实时分析布局与四大图表说明": {
        "en": (
            "Live Analysis Layouts & 4 Acoustic Plots",
            "• Switch between Live Monitor, Frequency Diagnosis, and Time-Frequency Tracking while preserving curves and zoom ranges.\n• CH-01 Waveform shows dynamics; CH-02 FFT shows harmonics; CH-03 Band Energy shows Sub/Bass/Mid/High balance; CH-04 Spectrogram tracks pitch & timbre over 30s.",
        ),
        "ko": (
            "실시간 분석 레이아웃 및 4대 차트 안내",
            "• 실시간 모니터 / 주파수 진단 / 시주파수 추적 레이아웃을 곡선과 줌 상태를 유지한 채 전환할 수 있습니다.\n• 파형(다이내믹), FFT 스펙트럼(배음), 대역 에너지(저/중/고음), 스펙트로그램(30초 시간-주파수)을 제공합니다.",
        ),
        "ja": (
            "リアルタイム解析レイアウト＆4大チャート",
            "• 「リアルタイムモニター / 周波数診断 / 時周波数追跡」を波形とズームを維持したまま切替可能です。\n• 波形・FFTスペクトル・帯域エネルギー・30秒スペクトログラムで音色と音程を可視化します。",
        ),
    },
    "和弦推测": {
        "en": (
            "Realtime Chord Estimation",
            "Matches the live 12-bin chroma vector against Major/Minor/7th templates with temporal smoothing to output chord symbol, chord tones, Roman degree, and stability score.",
        ),
        "ko": (
            "실시간 코드 추정",
            "실시간 12반음 크로마 벡터를 메이저/마이너/세븐스 템플릿과 비교하고 시간 평활화를 적용해 코드명, 구성음, 로마 도수 및 안정도를 표시합니다.",
        ),
        "ja": (
            "リアルタイムコード推定",
            "12半音クロマベクトルをメジャー/マイナー/セブンス等のテンプレートと照合し、時間平滑化によりコード名・構成音・ローマ度数・安定度を推定します。",
        ),
    },
    "调性推测": {
        "en": (
            "Krumhansl-Schmuckler Key Estimation",
            "Uses a 36-second sliding chroma profile to identify the tonal center (Key) and 2nd candidate, plus relative major/minor relation notes and modulation warnings.",
        ),
        "ko": (
            "Krumhansl-Schmuckler 조성 추정",
            "36초 슬라이딩 크로마 프로파일로 곡의 조성 중심(Key)과 2순위 후보, 나란한조 관계 및 전조 경고를 추정합니다.",
        ),
        "ja": (
            "Krumhansl-Schmuckler 調性推定",
            "36秒間のスライディングクロマ分布から調性中心(Key)と第2候補、平行調の関係、転調の可能性を推定します。",
        ),
    },
    "节拍器与 BPM": {
        "en": (
            "Tempo Detection & CPU Metronome",
            "Tracks onset periodicity over a 24s window to estimate BPM. Supports Tap Tempo, one-click Sync BPM, Overlay Click synced with A/B playback, 1-bar Count-In, and Standalone Click.",
        ),
        "ko": (
            "템포 감지 및 CPU 메트로놈",
            "24초 온셋 주기로 BPM을 추정합니다. 탭 템포, 감지 BPM 동기화, A/B 재생 연동 메트로놈, 1마디 카운트인 및 단독 메트로놈을 지원합니다.",
        ),
        "ja": (
            "テンポ検出＆CPUメトロノーム",
            "24秒窓のオンセット周期からBPMを推定。Tapテンポ、検出BPM同期、再生連動クリック、1小節カウントイン、単独メトロノームに対応します。",
        ),
    },
    "最近和弦进行与练习和弦工作流": {
        "en": (
            "Recent Chord Progression & Practice Workflow",
            "• Records the latest 12 stable chord transitions. In 'Chord & Degree' mode, displays compact single-line format (e.g. C[I] → G[V] → Am[vi]).\n• Click CHORD_PRACTICE to match common progressions, audition them, or export a Cubase-ready MIDI file.",
        ),
        "ko": (
            "최근 코드 진행 및 코드 연습 워크플로",
            "• 최근 12회의 안정적인 코드 전환을 기록하며 '코드명 + 도수' 모드에서 한 줄 컴팩트 형식(C[I] → G[V] → Am[vi])으로 표시합니다.\n• 코드 연습 버튼을 누르면 대표 진행 매칭, 미리듣기 및 Cubase 호환 MIDI 내보내기가 가능합니다.",
        ),
        "ja": (
            "直近コード進行＆コード練習ワークフロー",
            "• 直近12回の安定コード推移を記録。「コード名と度数」では C[I] → G[V] → Am[vi] の1行コンパクト形式で表示します。\n• 「コード練習」から定番進行の照合・試聴・Cubase互換MIDI出力が可能です。",
        ),
    },
    "移调 / Capo 与转调保护": {
        "en": (
            "Transpose / Capo & Modulation Protection",
            "Capo/Transpose only shifts displayed chord shapes and notation hints; underlying audio & MIDI pitch detection always stays anchored to concert pitch to prevent drift.",
        ),
        "ko": (
            "이조 / 카포 및 전조 보호",
            "카포/이조는 표시되는 코드 운지와 기보 힌트만 변환하며, 내부 오디오 및 MIDI 음고 감지는 항상 실음 기준으로 고정되어 전조 시 오차를 방지합니다.",
        ),
        "ja": (
            "移調 / カポ＆転調保護",
            "カポ/移調は表示コードと運指ヒントのみ変換し、内部の音声・MIDI音高検出は常に実音基準を維持するため転調時でもズレません。",
        ),
    },
    "SMTC 自动切歌重置": {
        "en": (
            "SMTC Auto Track-Change Reset",
            "Automatically clears chord history, key window, and BPM only after Windows Media Session (SMTC) confirms two consecutive track title changes — pausing or seeking will never reset.",
        ),
        "ko": (
            "SMTC 곡 변경 자동 리셋",
            "Windows 미디어 세션(SMTC)이 대상 플레이어의 곡 변경을 연속 2회 확인했을 때만 코드 이력·조성·BPM을 초기화합니다. 일시정지나 탐색 시에는 오작동하지 않습니다.",
        ),
        "ja": (
            "SMTC 曲変更自動リセット",
            "Windowsメディアセッション(SMTC)が曲変更を2回連続確認した場合のみコード履歴・調性・BPMを自動リセットします。一時停止やシークでは誤作動しません。",
        ),
    },
    "快速监听预设与贝斯独听增益": {
        "en": (
            "Quick Monitor Presets & Custom Bass Solo Gain",
            "• Quick Presets: One-click All / Inst Only / Vocals / Bass / Drums / Other solo combinations.\n• Bass Solo Boost: Default +12 dB (customizable 0–24 dB) with soft-clipping protection so low bass lines cut through clearly. Values >12 dB show a hearing warning. Check 'Apply Solo Gain on Export' to bake the boost into exported WAVs.",
        ),
        "ko": (
            "빠른 모니터 프리셋 및 베이스 독청 게인",
            "• 빠른 프리셋: 전체 / 반주만 / 보컬만 / 베이스만 / 드럼만 / 기타만 원클릭 전환.\n• 베이스 독청 게인: 기본 +12 dB(0–24 dB 직접 입력)로 저음을 선명하게 들려주며 소프트 리미터로 클리핑을 방지합니다. 12 dB 초과 시 청력 보호 경고가 표시됩니다.",
        ),
        "ja": (
            "クイックモニター＆ベース独聴ゲイン",
            "• プリセット: 全トラック / 伴奏のみ / ボーカル / ベース / ドラム / その他をワンクリック切替。\n• ベース独聴ゲイン: 既定+12dB（0〜24dB自由入力）で低音を明瞭化しソフトリミッターで歪み防止。12dB超は聴覚警告を表示し、出力WAVへの適用も選択可能です。",
        ),
    },
    "不变调倍速 (WSOLA) 与和弦段局部循环": {
        "en": (
            "Pitch-Preserving Speed (WSOLA) & Chord Sub-Loop",
            "• Time-Stretch (0.5x–1.25x): Pure-CPU WSOLA slows down or speeds up stem playback without changing pitch.\n• Loop Selected Chord: Highlight any bar/chord row in the table below and loop just that section.",
        ),
        "ko": (
            "음고유지 배속(WSOLA) 및 코드 구간 루프",
            "• 음고유지 배속(0.5x–1.25x): 순수 CPU WSOLA 알고리즘으로 음정 변화 없이 스템 재생 속도를 조절합니다.\n• 선택 코드 구간 루프: 아래 표에서 원하는 코드 구간을 선택해 해당 부분만 반복 연습합니다.",
        ),
        "ja": (
            "ピッチ維持倍速(WSOLA)＆コード区間ループ",
            "• ピッチ維持倍速(0.5x–1.25x): 純CPU WSOLA方式で音程を保ったままステムを遅く/速く再生します。\n• 選択コード区間ループ: 下表のコード行を選んでその小節だけ集中反復練習できます。",
        ),
    },
    "离线深度和弦、贝斯与鼓点分析": {
        "en": (
            "Offline Deep Chord, Bass Lowest Note & Drum Analysis",
            "Combines stem harmony, YIN bass fundamental tracking (reporting lowest note name, exact MIDI note number & modulation warnings), and drum transient detection. Check 'Extended Chords' to match maj7/m7/7/sus4.",
        ),
        "ko": (
            "오프라인 심층 코드·베이스 최저음·드럼 분석",
            "스템 화성 분석, YIN 베이스 기음 추적(최저 음명·정확한 MIDI 번호·전조 경고 출력) 및 드럼 트랜지언트 감지를 결합합니다. '확장 코드' 체크 시 maj7/m7/7/sus4도 매칭합니다.",
        ),
        "ja": (
            "オフライン詳細コード・ベース最低音・ドラム解析",
            "ステム和声解析、YINベース基音検出（最低音名・正確なMIDIノート番号・転調警告を出力）、ドラム過渡検出を統合。「拡張コード」で maj7/m7/7/sus4 にも対応します。",
        ),
    },
    "Cubase 兼容单轨 MIDI": {
        "en": (
            "Cubase-Compatible Standard MIDI",
            "Exports standard SMF Type-0 (480 PPQ) with Time Signature, Key Signature, Track Name, and Controller Reset at Tick 0, plus automatic overlap trimming for clean drag-and-drop into Cubase / DAWs.",
        ),
        "ko": (
            "Cubase 호환 단일 트랙 MIDI",
            "표준 SMF Type-0(480 PPQ) 형식으로 Tick 0에 박자표·조표·트랙명·CC 리셋을 기록하고 겹침 노트를 자동 정리해 Cubase 등 DAW에 바로 드래그 앤 드롭할 수 있습니다.",
        ),
        "ja": (
            "Cubase 互換スタンダード MIDI",
            "標準SMF Type-0 (480 PPQ) 形式で Tick 0 に拍子・調号・トラック名・CCリセットを挿入し、重複ノートを自動整理するため Cubase 等のDAWへそのままドラッグ投入できます。",
        ),
    },
    "16 步鼓点律动网格与鼓点 MIDI 导出": {
        "en": (
            "16-Step Drum Groove Grid & Drum MIDI Export",
            "Quantizes isolated drum stems into a 1-bar 16th-note grid showing Kick, Snare, and Hi-Hat patterns. Supports instant drum preview and GM Channel 10 MIDI export.",
        ),
        "ko": (
            "16스텝 드럼 그루브 그리드 및 드럼 MIDI 내보내기",
            "분리된 드럼 스템을 1마디 16분음표 그리드로 양자화해 킥/스네어/하이햇 패턴을 시각화합니다. 즉시 드럼 미리듣기와 GM 채널 10 MIDI 내보내기를 지원합니다.",
        ),
        "ja": (
            "16ステップドラムグリッド＆ドラム MIDI 出力",
            "分離ドラムステムを1小節16分音符グリッドに量子化し、キック・スネア・ハイハットのリズムを可視化。即時試聴とGMチャンネル10 MIDI出力に対応します。",
        ),
    },
    "16GB RAM / 8GB VRAM 资源看门狗说明": {
        "en": (
            "16GB RAM / 8GB VRAM Resource Watchdog",
            "• 3-Process Isolation: Core UI stays lightweight; AI stem separation and Basic Pitch MIDI run in dedicated worker subprocesses and release 100% RAM/VRAM upon exit.\n• Watchdog enforces thresholds and auto-triggers E-STOP if system memory drops critically low.",
        ),
        "ko": (
            "16GB RAM / 8GB VRAM 리소스 워치독 안내",
            "• 3프로세스 격리: 메인 UI는 초경량을 유지하며 AI 분리와 MIDI 변환은 별도 워커 프로세스에서 실행 후 종료 시 메모리를 100% 반환합니다.\n• 시스템 메모리가 위험 수준에 도달하면 자동으로 긴급 정지합니다.",
        ),
        "ja": (
            "16GB RAM / 8GB VRAM リソース監視ウォッチドッグ",
            "• 3プロセス完全分離: メインUIは軽量に保ち、AI分離とMIDI転写は独立ワーカーで実行・終了時にメモリを100%解放します。\n• メモリ危険水準では自動で緊急停止します。",
        ),
    },
    "系统设置总览": {
        "en": (
            "System Settings Overview",
            "• Appearance & Layout: Switch Acid Light/Dark/System themes, 4 languages, frameless shell, help mode, focus animations, and portable app-adjacent storage.\n• Resource Guardrails: Tuned for 8GB VRAM & 16GB RAM plus optional Plan A/B Hybrid iGPU+dGPU offload.\n• AI & MIDI Runtime: Auto-scan local PyTorch or run one-click turnkey setup.",
        ),
        "ko": (
            "시스템 설정 개요",
            "• 외관 및 레이아웃: 애시드 라이트/다크/시스템 테마, 4개 언어, 프레임 없는 창, 설명 모드, 포커스 애니메이션 및 포터블 저장소 설정.\n• 리소스 보호: 8GB VRAM·16GB RAM 안전 임계값 및 선택형 내장+외장 GPU 하이브리드 가속.\n• AI & MIDI 환경: 로컬 PyTorch 자동 스캔 및 원클릭 구성.",
        ),
        "ja": (
            "システム設定の概要",
            "• 外観とレイアウト: アシッド明暗/システム切替・4言語・フレームレス・説明モード・フォーカスアニメ・同階層ポータブル保存を設定。\n• リソース保護: 8GB VRAM・16GB RAM保護閾値および任意のiGPU+dGPU協調加速。\n• AI & MIDI環境: ローカルPyTorch検出と一括構築。",
        ),
    },
    "自定义外观与实时预览": {
        "en": (
            "Customize Appearance & Live Preview",
            "Defaults to Acid Telemetry Clinical Light (industrial font & palette locked, 11–20px size adjustable). Switch to Classic/Lenso/Graphite/Warm Sand to customize colors, OS fonts, and upload custom wallpapers.",
        ),
        "ko": (
            "외관 사용자 지정 및 실시간 미리보기",
            "기본값은 애시드 텔레메트리 라이트(표준 글꼴/색상 잠금, 11–20px 크기 조절 가능)입니다. 다른 테마로 전환하면 색상·시스템 글꼴·사용자 배경 이미지를 자유롭게 설정할 수 있습니다.",
        ),
        "ja": (
            "外観カスタマイズ＆リアルタイムプレビュー",
            "既定はアシッドテレメトリ（ライト）で工業フォントと公式配色がロックされ文字サイズ11–20pxを調整可能。他テーマでは色・PCフォント・カスタム壁紙も自由に設定できます。",
        ),
    },
    "同级便携存储机制": {
        "en": (
            "App-Adjacent Portable Storage",
            "Whenever the app folder is writable, settings.json, temporary separation caches, and WAV/MIDI exports stay right next to the app instead of cluttering C: drive; falls back to user home only if read-only.",
        ),
        "ko": (
            "동일 폴더 포터블 저장 방식",
            "앱 폴더에 쓰기 권한이 있으면 settings.json, 임시 분리 캐시 및 WAV/MIDI 내보내기가 모두 앱과 같은 폴더에 저장되어 C드라이브를 어지럽히지 않습니다.",
        ),
        "ja": (
            "同階層ポータブル保存方式",
            "アプリフォルダが書き込み可能であれば settings.json・一時分離キャッシュ・WAV/MIDI出力をすべてアプリ同階層に保存し、Cドライブを汚しません（読取専用時のみユーザーフォルダへ退避）。",
        ),
    },
    "项目仓库与反馈说明": {
        "en": (
            "Project Repository & Feedback",
            "Open the GitHub repository page or Issues tracker in your browser, or copy the repository URL with one click.",
        ),
        "ko": (
            "프로젝트 저장소 및 피드백",
            "아래 버튼을 눌러 브라우저에서 GitHub 저장소나 Issues 피드백 페이지로 바로 이동하거나 URL을 복사할 수 있습니다.",
        ),
        "ja": (
            "プロジェクトURL・フィードバック",
            "ボタンをクリックするとブラウザでGitHubリポジトリやIssuesページを開いたり、URLをワンクリックでコピーできます。",
        ),
    },
    "系统诊断表说明": {
        "en": (
            "System Diagnostics Table",
            "Reports OS Build, available RAM, NVIDIA GPU & free VRAM, plus PyTorch CUDA / Blackwell sm_120 support inside the isolated AI runtime.",
        ),
        "ko": (
            "시스템 진단표 설명",
            "현재 PC의 OS 빌드, 가용 RAM, NVIDIA GPU 및 여유 VRAM, 격리 AI 환경의 PyTorch CUDA / Blackwell sm_120 지원 상태를 표시합니다.",
        ),
        "ja": (
            "システム診断表の説明",
            "OSビルド、空きRAM、NVIDIA GPUと空きVRAM、独立AI環境内のPyTorch CUDA / Blackwell sm_120対応状況を表示します。",
        ),
    },
    "分轨前内存提醒阈值": {
        "en": (
            "Pre-Split RAM Warning Threshold",
            "Shows a yellow caution notice before launching AI separation when system available RAM drops below this value (default 5120 MB), while still allowing execution.",
        ),
        "ko": (
            "분리 전 메모리 경고 임계값",
            "시스템 가용 RAM이 이 값(기본 5120 MB) 미만이면 노란색 경고를 표시하되 분리 실행은 허용합니다.",
        ),
        "ja": (
            "分離前メモリ警告しきい値",
            "システム空きRAMがこの値（既定 5120 MB）を下回ると黄色警告を表示しますが、分離実行は継続可能です。",
        ),
    },
    "拒绝新分轨阈值": {
        "en": (
            "Refuse New Split RAM Floor",
            "Blocks starting new AI separation jobs when available system RAM falls below this limit (default 3072 MB) to prevent system freezes.",
        ),
        "ko": (
            "신규 분리 거부 RAM 하한",
            "시스템 가용 RAM이 이 값(기본 3072 MB) 미만이면 시스템 멈춤 방지를 위해 새 AI 분리 작업 시작을 거부합니다.",
        ),
        "ja": (
            "新規分離拒否メモリ下限",
            "空きRAMがこの値（既定 3072 MB）未満の場合、システムフリーズ防止のため新規AI分離タスクの開始をブロックします。",
        ),
    },
    "紧急停止 (E-STOP) 内存阈值": {
        "en": (
            "Emergency Stop (E-STOP) RAM Floor",
            "Immediately terminates the running AI subprocess and reclaims memory if system available RAM falls below this critical floor (default 2048 MB).",
        ),
        "ko": (
            "긴급 정지(E-STOP) 임계 RAM",
            "분리 실행 중 시스템 가용 RAM이 이 임계치(기본 2048 MB) 이하로 떨어지면 AI 하위 프로세스를 즉시 종료하고 메모리를 회수합니다.",
        ),
        "ja": (
            "緊急停止 (E-STOP) メモリしきい値",
            "分離実行中に空きRAMがこの危険水準（既定 2048 MB）を下回ると、AIサブプロセスを即時終了してメモリを回収します。",
        ),
    },
    "2 轨快速分离显存预检": {
        "en": (
            "2-Stem Free VRAM Pre-Check",
            "Minimum free GPU VRAM required before starting 2-Stem (Vocals + Instrumental MDX-ONNX) on GPU (default 4096 MB).",
        ),
        "ko": (
            "2-Stem 빠른 분리 VRAM 사전 점검",
            "GPU에서 2-Stem(보컬+반주 MDX ONNX) 분리를 시작하기 위한 최소 여유 VRAM입니다.",
        ),
        "ja": (
            "2-Stem 分離の空きVRAM事前チェック",
            "GPUで2-Stem（ボーカル＋伴奏 MDX ONNX）を開始するために必要な最小空きVRAMです。",
        ),
    },
    "4 轨精细分离显存预检": {
        "en": (
            "4-Stem Free VRAM Pre-Check",
            "Minimum free GPU VRAM required before starting 4-Stem (Vocals/Drums/Bass/Other HTDemucs) on GPU (default 5632 MB).",
        ),
        "ko": (
            "4-Stem 정밀 분리 VRAM 사전 점검",
            "GPU에서 4-Stem(보컬/드럼/베이스/기타 HTDemucs) 분리를 시작하기 위한 최소 여유 VRAM입니다.",
        ),
        "ja": (
            "4-Stem 分離の空きVRAM事前チェック",
            "GPUで4-Stem（ボーカル/ドラム/ベース/その他 HTDemucs）を開始するために必要な最小空きVRAMです。",
        ),
    },
    "桌面与音乐播放器保底显存": {
        "en": (
            "Reserved Desktop & Player VRAM Cushion",
            "Minimum VRAM always kept free for Windows DWM desktop compositor, music players, and browser tabs.",
        ),
        "ko": (
            "데스크톱 및 플레이어 예약 VRAM",
            "Windows 데스크톱 컴포지터(DWM), 음악 플레이어 및 브라우저를 위해 항상 남겨두는 VRAM 안전 마진입니다.",
        ),
        "ja": (
            "デスクトップ＆再生アプリ用確保VRAM",
            "Windowsデスクトップ描画(DWM)・音楽プレーヤー・ブラウザ用に常に確保しておく安全マージンVRAMです。",
        ),
    },
    "流式分块与 8GB 显存保护": {
        "en": (
            "Streaming Chunk Size & 8GB VRAM Guard",
            "Long audio is split into overlapping chunks fed sequentially into the AI worker to cap peak VRAM/RAM on 8GB/16GB hardware (recommended: 6.0s).",
        ),
        "ko": (
            "스트리밍 청크 및 8GB VRAM 보호",
            "긴 오디오를 고정 길이의 중첩 청크로 나누어 순차 추론함으로써 8GB VRAM / 16GB RAM 피크 초과를 방지합니다(권장 6.0초).",
        ),
        "ja": (
            "ストリーミング分割＆8GB VRAM保護",
            "長い音声を固定秒数の重複チャンクへ分割し逐次推論することで、8GB VRAM/16GB RAM環境でのピーク溢れを防ぎます（推奨 6.0秒）。",
        ),
    },
    "HTDemucs 内部模型分段": {
        "en": (
            "HTDemucs Internal Segment Length",
            "Controls the single-window inference segment for 4-Stem HTDemucs (4–10s, default 6s). Automatically steps down on OOM without affecting 2-Stem MDX.",
        ),
        "ko": (
            "HTDemucs 내부 모델 세그먼트",
            "4-Stem HTDemucs 단일 추론 창 길이(4–10초, 기본 6초)를 제어합니다. VRAM 부족 시 자동으로 낮추어 재시도합니다.",
        ),
        "ja": (
            "HTDemucs 内部セグメント長",
            "4-Stem HTDemucs の単一推論窓長（4–10秒・既定6秒）を制御します。VRAM不足時は自動縮小し2-Stem MDXには影響しません。",
        ),
    },
    "实验性 BS-RoFormer 模型开关": {
        "en": (
            "Experimental BS-RoFormer Toggle",
            "BS-RoFormer offers fine vocal detail but uses significantly more VRAM than MDX/HTDemucs. Disabled by default to protect 8GB VRAM.",
        ),
        "ko": (
            "실험적 BS-RoFormer 모델 스위치",
            "BS-RoFormer는 음질이 섬세하지만 MDX/HTDemucs보다 VRAM 소모가 훨씬 큽니다. 8GB VRAM 보호를 위해 기본 비활성화되어 있습니다.",
        ),
        "ja": (
            "実験的 BS-RoFormer モデル切替",
            "BS-RoFormerは高精度ですがMDX/HTDemucsよりVRAM消費が大きいため、8GB VRAM保護のため既定オフになっています。",
        ),
    },
    "方案 A：核显 DirectML + 独显 CUDA 异构分工": {
        "en": (
            "Plan A: DirectML iGPU + CUDA dGPU Heterogeneous Offload",
            "• NVIDIA dGPU (cuda:0) stays dedicated to heavy 4-Stem HTDemucs and MIDI transcription.\n• AMD/Intel iGPU handles lightweight 2-Stem MDX-Net ONNX & live split via onnxruntime-directml (DmlExecutionProvider), keeping 2-Stem splitting responsive even while the dGPU is busy gaming.\n• Falls back safely to CUDA/CPU if onnxruntime-directml is not installed.",
        ),
        "ko": (
            "방안 A: 내장 GPU DirectML + 외장 GPU CUDA 이기종 분업",
            "• NVIDIA 외장 GPU(cuda:0)는 고부하 4-Stem HTDemucs 및 MIDI 채보를 전담합니다.\n• AMD/Intel 내장 GPU는 onnxruntime-directml(DmlExecutionProvider)로 경량 2-Stem MDX-Net ONNX 분리를 맡아 외장 GPU가 바쁠 때도 백그라운드 분리가 가능합니다.\n• 미설치 시 자동으로 CUDA/CPU로 안전하게 폴백합니다.",
        ),
        "ja": (
            "プランA: 内蔵GPU DirectML ＋ 外付けGPU CUDA 異種分担",
            "• NVIDIA dGPU (cuda:0) は高負荷な 4-Stem HTDemucs と MIDI 転写に専念します。\n• AMD/Intel 内蔵GPUは onnxruntime-directml (DmlExecutionProvider) で軽量 2-Stem MDX-Net ONNX を処理し、dGPU使用中でも2ステム分離が可能です。\n• 未導入時は自動でCUDA/CPUへ安全にフォールバックします。",
        ),
    },
    "方案 B：图形渲染与 AI 推理物理隔离": {
        "en": (
            "Plan B: Physical GUI Render vs AI Compute Isolation",
            "• Pins background AI worker subprocesses to CUDA_VISIBLE_DEVICES=0 (PCI_BUS_ID) on the NVIDIA dGPU.\n• Click 'Windows Graphics Settings' to assign ListenScope GUI & PyQtGraph rendering to Power Saving (AMD/Intel iGPU), eliminating desktop frame drops under heavy AI load.",
        ),
        "ko": (
            "방안 B: 그래픽 렌더링과 AI 추론 물리 격리",
            "• 활성화 시 백그라운드 AI 워커를 CUDA_VISIBLE_DEVICES=0(PCI_BUS_ID)으로 외장 NVIDIA GPU에 고정합니다.\n• 'Windows 그래픽 설정'에서 ListenScope 메인 앱을 절전(내장 GPU)으로 지정하면 AI 풀로드 중에도 UI 프레임 드랍이 사라집니다.",
        ),
        "ja": (
            "プランB: GUI描画とAI推論の物理分離",
            "• 有効化するとバックグラウンドAIワーカーを CUDA_VISIBLE_DEVICES=0 (PCI_BUS_ID) でNVIDIA dGPUへ固定します。\n• 「Windows グラフィック設定」でListenScope本体を省電力(内蔵GPU)に設定すると、AI高負荷時でもUIのフレーム落ちを防げます。",
        ),
    },
    "本地 cu128 Wheel 与短路径安装": {
        "en": (
            "Local cu128 Wheels & Short-Path Setup",
            "If downloading the 2.75GB PyTorch cu128 package is slow, place matching torch/torchaudio/torchvision .whl files in one folder and browse here. MIDI env uses short path `m` / `.venv-midi` to avoid Windows MAX_PATH failures.",
        ),
        "ko": (
            "로컬 cu128 Wheel 및 단축 경로 설치",
            "2.75GB PyTorch cu128 다운로드가 느리면 해당 .whl 파일들을 한 폴더에 넣고 여기에서 지정할 수 있습니다. MIDI 환경은 Windows 경로 길이 제한을 피하기 위해 단축 경로 `m`을 사용합니다.",
        ),
        "ja": (
            "ローカル cu128 Wheel ＆短縮パス導入",
            "2.75GBのPyTorch cu128取得が遅い場合、該当 .whl を1フォルダにまとめて指定できます。MIDI環境はWindowsパス長制限回避のため短縮パス `m` を使用します。",
        ),
    },
    "什么是「步数 (N 步)」与和弦练习怎么用？": {
        "en": (
            "What Does 'N steps' Mean & How to Use Chord Practice",
            "• '4 steps / 2 steps' counts how many consecutive chords in a progression match your song's recent chord trajectory (higher = closer match). 'Common Practice' lists classic progressions in the chosen key.\n• Workflow: 1) Confirm Practice Key; 2) Click any row (Roman degrees & chord names); 3) Click Audition Progression to hear it at your BPM; 4) Click Export Progression MIDI to drop straight into Cubase.",
        ),
        "ko": (
            "'N스텝'의 의미와 코드 연습 사용법",
            "• '4스텝 / 2스텝'은 추천 진행 중 현재 곡의 최근 코드 흐름과 연속 일치한 코드 개수를 뜻합니다(높을수록 원곡과 가까움). '일반 연습'은 해당 조성의 대표 진행입니다.\n• 사용법: 1) 연습 조성 확인 → 2) 원하는 진행 행 선택 → 3) '진행 미리듣기'로 템포별 청음 → 4) '진행 MIDI 내보내기'로 Cubase 등에 바로 활용.",
        ),
        "ja": (
            "「Nステップ」の意味とコード練習の使い方",
            "• 「4ステップ / 2ステップ」は現在の曲の直近コード推移と連続一致したコード数を表します（多いほど原曲に近い進行）。「定番練習」はその調の代表的進行です。\n• 使い方: 1) 練習キー確認 → 2) 表から進行を選択 → 3)「進行を試聴」で任意BPM再生 → 4)「進行 MIDI を出力」でCubase等へ投入。",
        ),
    },
    "Cubase 兼容标准 MIDI": {
        "en": (
            "Cubase-Ready Standard MIDI Export",
            "Exports SMF Type-0 (480 PPQ) with English track name, Time Signature, Tempo, Key Signature, Reset All CC (121=0), and Program Change at Tick 0; saved into the app-adjacent exports folder.",
        ),
        "ko": (
            "Cubase 호환 표준 MIDI 내보내기",
            "Tick 0에 영문 트랙명, 박자표, BPM, 조표, Reset All CC(121=0) 및 음색 번호가 기록된 SMF Type-0(480 PPQ) 표준 MIDI를 앱 동일 폴더의 exports에 저장합니다.",
        ),
        "ja": (
            "Cubase 互換スタンダード MIDI 出力",
            "Tick 0 に英語トラック名・拍子・BPM・調号・Reset All CC(121=0)・プログラムチェンジを書き込んだ SMF Type-0 (480 PPQ) を同階層の exports フォルダへ保存します。",
        ),
    },
    "实时和弦推测与稳定度": {
        "en": (
            "Realtime Chord Estimation & Stability",
            "• Matches live 12-bin chroma vectors against 24 Major/Minor templates via cosine similarity.\n• Roman Degree automatically maps the active chord into the detected key (e.g., Am = vi in C major).\n• Higher correlation and larger margin over 2nd candidate light up more dots on the right stability matrix.",
        ),
        "ko": (
            "실시간 코드 추정 및 안정도",
            "• 12반음 크로마 벡터와 24개 장/단 3화음 템플릿의 코사인 유사도를 매칭합니다.\n• 상대 도수는 현재 주조 기준 로마 숫자 도수(예: C장조의 Am = vi)를 자동 계산합니다.\n• 상관도와 2순위 격차가 클수록 오른쪽 도트 매트릭스가 더 많이 점등됩니다.",
        ),
        "ja": (
            "リアルタイムコード推定＆安定度",
            "• 12半音クロマベクトルを24種のメジャー/マイナー和音テンプレートとコサイン類似度で照合します。\n• 相対度数は検出キーに対するローマ度数（例: CメジャーでのAm = vi）を自動算出します。\n• 相関が高く第2候補との差が大きいほど右側のドットマトリクスが多く点灯します。",
        ),
    },
    "K-S 滑动窗口调性推测与转调预警": {
        "en": (
            "K-S Sliding Window Key Estimation & Modulation Alert",
            "• Runs Krumhansl-Schmuckler tonal profile correlation over a 15–30s sliding chroma window.\n• Displays Relative Major/Minor relationships (e.g., C major / A minor) and flags possible key modulations.",
        ),
        "ko": (
            "K-S 슬라이딩 윈도우 조성 추정 및 전조 경고",
            "• 최근 15–30초 크로마 분포에 Krumhansl-Schmuckler 인지 음계 프로파일을 적용해 조성을 추정합니다.\n• 나란한조 관계(예: C major / A minor)와 전조 가능성을 표시합니다.",
        ),
        "ja": (
            "K-S スライディング窓 調性推定＆転調警告",
            "• 直近15〜30秒のクロマ分布に Krumhansl-Schmuckler 法を適用して主調を推定します。\n• 平行調（例: C major / A minor）の関係や転調の兆候を警告表示します。",
        ),
    },
    "BPM 节拍、主音高与音分偏差条": {
        "en": (
            "BPM Tempo, Dominant Pitch & Cents Deviation Meter",
            "• BPM tracks onset autocorrelation peaks; click 'Sync BPM' to copy into the metronome.\n• Pitch displays the dominant fundamental note name, Hz, and cents tuning offset bar.",
        ),
        "ko": (
            "BPM 템포, 기본 음고 및 센트 편차 바",
            "• BPM은 온셋 자기상관 피크로 속도를 추정하며 '감지 BPM 동기화'로 메트로놈에 즉시 적용할 수 있습니다.\n• 음고 미터는 현재 가장 뚜렷한 기음의 음명, Hz, 센트 편차를 실시간 표시합니다.",
        ),
        "ja": (
            "BPMテンポ・基本ピッチ＆セント偏差バー",
            "• BPMはオンセット自己相関ピークから推定し、「検出BPM同期」でメトロノームへ即反映できます。\n• ピッチメーターは最有力基音の音名・Hz・セント偏差をリアルタイム表示します。",
        ),
    },
    "Tap 定速与纯 CPU 节拍器": {
        "en": (
            "Tap Tempo & Pure-CPU Metronome",
            "Click 'Tap Tempo' two or more times to lock onto any groove. Both 'Overlay Click' and 'Count-In (1 Bar)' are synthesized purely on CPU and automatically follow 0.5x–1.25x speed changes.",
        ),
        "ko": (
            "탭 템포 및 순수 CPU 메트로놈",
            "'탭 템포'를 2회 이상 누르면 속도를 즉시 추정합니다. 재생 연동 메트로놈과 1마디 카운트인은 순수 CPU 합성으로 0.5x–1.25x 배속 변화에 자동 동기화됩니다.",
        ),
        "ja": (
            "Tapテンポ＆純CPUメトロノーム",
            "「Tapテンポ」を2回以上押すと即座にBPMを算出します。再生連動クリックと1小節カウントインは純CPU合成で 0.5x–1.25x 変速にも自動追従します。",
        ),
    },
    "独立 AI 分轨环境说明": {
        "en": (
            "Isolated AI Separation Runtime",
            "Keeping the multi-GB PyTorch CUDA stack inside a separate worker environment keeps the main ListenScope UI lightweight with zero VRAM usage when idle, and releases 100% VRAM the instant separation finishes.",
        ),
        "ko": (
            "독립 AI 분리 환경 안내",
            "수 GB 규모의 PyTorch CUDA를 별도 하위 프로세스 환경으로 격리하여 대기 중에는 메인 앱이 초경량·VRAM 0MB를 유지하고, 분리 종료 즉시 VRAM을 100% 반환합니다.",
        ),
        "ja": (
            "独立 AI 分離環境について",
            "数GBのPyTorch CUDAを独立ワーカー環境へ分離することで、待機中のメインUIは超軽量・VRAM消費ゼロを保ち、分離終了と同時にVRAMを100%解放します。",
        ),
    },
    "独立 CPU MIDI 环境说明": {
        "en": (
            "Isolated CPU MIDI Runtime (Basic Pitch)",
            "Spotify Basic Pitch requires TensorFlow 2.15 (Python 3.11 only). Isolating it in its own CPU environment prevents dependency conflicts with PyTorch CUDA and avoids competing for 8GB VRAM.",
        ),
        "ko": (
            "독립 CPU MIDI 환경 안내 (Basic Pitch)",
            "Spotify Basic Pitch는 TensorFlow 2.15(Python 3.11 전용)를 필요로 합니다. 독립 CPU 환경에 격리해 PyTorch CUDA와의 충돌 및 8GB VRAM 경합을 완전히 방지합니다.",
        ),
        "ja": (
            "独立 CPU MIDI 環境について (Basic Pitch)",
            "Spotify Basic Pitch は TensorFlow 2.15（Python 3.11専用）を必要とします。独立CPU環境へ分離することでPyTorch CUDAとの競合や8GB VRAM圧迫を防ぎます。",
        ),
    },
    "原曲快照参考 (SNAPSHOT_ONLY) 与和弦练习怎么用？": {
        "en": (
            "Song Snapshot (SNAPSHOT_ONLY) & Chord Practice Guide",
            "• Snapshot Freeze: Opening this dialog freezes the song's detected key, BPM, and recent chord trajectory so background audio changes won't interrupt practice.\n• How to Use: 1) Check/pick Practice Key; 2) Select a progression row; 3) Click Audition to hear it at your BPM; 4) Export as Cubase-ready MIDI.",
        ),
        "ko": (
            "원곡 스냅샷(SNAPSHOT_ONLY) 및 코드 연습 가이드",
            "• 스냅샷 고정: 창을 열 때 현재 감지된 조성·BPM·최근 코드 흐름을 고정해 백그라운드 곡 변경에 방해받지 않습니다.\n• 사용법: 1) 연습 조성 선택 → 2) 진행 행 클릭 → 3) 미리듣기 → 4) Cubase 호환 MIDI 내보내기.",
        ),
        "ja": (
            "原曲スナップショット (SNAPSHOT_ONLY) とコード練習ガイド",
            "• スナップショット固定: ダイアログを開いた時点の検出キー・BPM・直近コード進行を凍結し、再生中の曲変更に影響されず練習できます。\n• 使い方: 1) 練習キー選択 → 2) 進行行を選択 → 3) 試聴 → 4) Cubase互換MIDI出力。",
        ),
    },
    "练习调与指型口径": {
        "en": (
            "Practice Key & Capo Shape Convention",
            "When Capo/Transpose is active, select the chord-shape key as seen by a guitarist; the table shows transposed shapes while audition and MIDI export automatically convert back to true concert pitch.",
        ),
        "ko": (
            "연습 조성 및 카포 운지 기준",
            "이조/카포가 적용된 경우 기타리스트 기준의 운지 조성을 선택하면 표에는 운지 코드가 표시되고, 미리듣기와 MIDI 내보내기는 실제 발음 음고로 자동 변환됩니다.",
        ),
        "ja": (
            "練習キーとカポ運指の仕様",
            "カポ/移調が有効な場合、ギタリスト視点のフォームキーを選ぶと表は運指コードで表示され、試聴とMIDI出力は自動的に実音ピッチへ変換されます。",
        ),
    },
    "练习速度与匹配步数说明": {
        "en": (
            "Practice Tempo (BPM) & Matched Steps Explained",
            "• Tempo (BPM): Defaults to 4 beats (1 bar) per chord; adjusting BPM updates both local audition and exported MIDI tempo.\n• Recent Match ('N steps' vs 'Common Practice'): 'N steps' counts how many chords consecutively match your song's recent progression; 'Common Practice' provides classic progressions in this key.",
        ),
        "ko": (
            "연습 템포(BPM) 및 일치 스텝 설명",
            "• 연습 템포(BPM): 기본 코드당 4박(1마디)이며 BPM 조절이 미리듣기와 MIDI 내보내기에 즉시 반영됩니다.\n• 최근 코드 일치('N스텝' / '일반 연습'): N스텝은 원곡 최근 코드 흐름과 연속 일치한 개수이며, 일반 연습은 해당 조성의 대표 진행입니다.",
        ),
        "ja": (
            "練習テンポ(BPM)と一致ステップ数の説明",
            "• 練習テンポ(BPM): 既定は1コード4拍（1小節）で、BPM変更は試聴とMIDI出力の両方に即反映されます。\n• 直近コード一致（「Nステップ」/「定番練習」）: Nステップは曲の直近進行と連続一致したコード数、定番練習はその調の王道進行です。",
        ),
    },
    "LEVEL // RMS · 平均电平 · RMS": {
        "en": (
            "LEVEL // RMS · Average Level",
            "RMS (Root Mean Square) reflects perceived average loudness in dBFS (0 dBFS = digital full scale).",
        ),
        "ko": (
            "LEVEL // RMS · 평균 레벨",
            "RMS(제곱평균제곱근)는 사람이 인지하는 평균 음량을 dBFS 단위로 표시합니다(0 dBFS = 풀스케일).",
        ),
        "ja": (
            "LEVEL // RMS · 平均レベル",
            "RMS（実効値）は人間の聴感に近い平均音量を dBFS 単位で示します（0 dBFS = フルスケール）。",
        ),
    },
    "PEAK // dBFS · 峰值电平": {
        "en": (
            "PEAK // dBFS · Peak Level",
            "Instantaneous maximum sample amplitude in the current analysis frame; approaching 0.0 dBFS indicates clipping risk.",
        ),
        "ko": (
            "PEAK // dBFS · 피크 레벨",
            "현재 분석 프레임의 순간 최대 샘플 진폭입니다. 0.0 dBFS에 가까우면 디지털 클리핑 위험이 있습니다.",
        ),
        "ja": (
            "PEAK // dBFS · ピークレベル",
            "現在フレームの瞬間最大振幅です。0.0 dBFS に近づくとデジタルクリッピング（音割れ）の恐れがあります。",
        ),
    },
    "PITCH // F0 · 主音高": {
        "en": (
            "PITCH // F0 · Dominant Pitch",
            "Tracks the most prominent fundamental pitch in realtime using YIN / autocorrelation (note name, Hz, and cents offset).",
        ),
        "ko": (
            "PITCH // F0 · 기본 음고",
            "YIN / 자기상관 기음 추적 알고리즘으로 현재 가장 뚜렷한 음고(음명, Hz, 센트 편차)를 실시간 표시합니다.",
        ),
        "ja": (
            "PITCH // F0 · 基本ピッチ",
            "YIN / 自己相関アルゴリズムで現在最も顕著な基本音高（音名・Hz・セント偏差）をリアルタイム追跡します。",
        ),
    },
    "RING // BUFFER · 历史缓冲": {
        "en": (
            "RING // BUFFER · 120s Ring Buffer",
            "Valid audio duration stored in the fixed 120-second RAM ring buffer (~43.95 MiB raw PCM cap; never grows unbounded).",
        ),
        "ko": (
            "RING // BUFFER · 120초 순환 버퍼",
            "고정 120초 RAM 순환 버퍼에 기록된 유효 오디오 길이입니다(원본 PCM 약 43.95 MiB 상한으로 무한 증가하지 않음).",
        ),
        "ja": (
            "RING // BUFFER · 120秒リングバッファ",
            "固定120秒RAMリングバッファに蓄積された有効音声長です（生PCM上限約43.95 MiB、無制限に増加しません）。",
        ),
    },
    "静态锁定 (STATIC_LOCK) 与遥测微动画": {
        "en": (
            "STATIC_LOCK & Telemetry Micro-Animations",
            "• The pulsing dots, header meter bars, and segmented battery cells are lightweight telemetry micro-animations that can scale with live audio dynamics and climax.\n• Toggle [STATIC_LOCK] to immediately freeze spectrum/chord refreshes and all animations for clean score reading, screenshots, or minimum power draw.",
        ),
        "ko": (
            "STATIC_LOCK 및 텔레메트리 미세 애니메이션",
            "• 카드의 점멸 도트, 상단 미터 바 및 분할 배터리 진행률 바는 음악 에너지와 클라이맥스에 연동되는 경량 텔레메트리 애니메이션입니다.\n• [STATIC_LOCK]을 누르면 메인 스펙트럼/코드 갱신과 모든 애니메이션을 즉시 고정하여 악보 읽기·캡처 및 절전 모드로 전환됩니다.",
        ),
        "ja": (
            "静的ロック (STATIC_LOCK) とテレメトリ演出",
            "• ドット点滅・上部パルスバー・電池型セグメントバーは楽曲の音量や盛り上がりに合わせて反応する軽量テレメトリ演出です。\n• [STATIC_LOCK] を押すとメイン画面のスペクトル/コード更新と全アニメーションを即時凍結し、譜面確認・スクリーンショット・省電力に最適です。",
        ),
    },
    "控件边框质感与托盘驻留": {
        "en": (
            "Button Edge Finish & System Tray Behavior",
            "• Edge Finish: Choose between Tactile Rim, Soft Bevel, or Pure Flat button & card borders (adjustable even under Acid Telemetry).\n• Minimize to Tray: Clicking the window close (×) button sends ListenScope to the Windows system tray instead of exiting; use the tray right-click menu to quit completely.",
        ),
        "ko": (
            "컨트롤 테두리 질감 및 시스템 트레이 동작",
            "• 테두리 질감: '입체 미세 테두리 / 미세 베벨 / 플랫 스타일' 중 선택할 수 있으며 애시드 테마에서도 자유롭게 조정됩니다.\n• 시스템 트레이: 창 닫기(×) 클릭 시 종료 대신 트레이로 최소화하며 트레이 우클릭 메뉴에서 완전히 종료할 수 있습니다.",
        ),
        "ja": (
            "ボタン質感とシステムトレイ常駐",
            "• 質感スタイル:「立体リムエッジ」「ソフトベベル」「ピュアフラット」を Acid テーマ下でも好みに応じて切替できます。\n• トレイ常駐: 右上の×ボタンで終了せずトレイへ格納し、トレイアイコンの右クリックメニューから完全終了できます。",
        ),
    },
    "遥测微动画强度与音乐联动": {
        "en": (
            "Telemetry Animation Intensity & Music Sync",
            "Controls the motion intensity (0% = completely static, 100% = full pulse) of dot matrices, meter bars, and segmented battery bars.\nEnable Music Sync to make them surge organically with audio volume and musical climax; use [STATIC_LOCK] on the footer bar to freeze anytime.",
        ),
        "ko": (
            "텔레메트리 애니메이션 강도 및 음악 연동",
            "도트 매트릭스, 상단 미터, 배터리 분할 진행률 바의 움직임 강도(0% = 완전 정지, 100% = 최대 펄스)를 조절합니다.\n음악 에너지·클라이맥스 연동을 켜면 실시간 음량과 고조 구간에 맞춰 강도가 반응하며 하단 [STATIC_LOCK]으로 언제든 정지할 수 있습니다.",
        ),
        "ja": (
            "テレメトリ演出強度＆音楽リアルタイム連動",
            "ドット・パルスバー・電池型セグメントの駆動強度（0%=完全静止、100%=フル演出）を調整します。\n楽曲連動をオンにすると音量やサビの盛り上がりに応じて自然に強まり、下部 [STATIC_LOCK] でいつでも凍結できます。",
        ),
    },
}
