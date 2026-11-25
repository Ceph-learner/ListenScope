"""Four-language UI localization (简体中文 zh, English en, 한국어 ko, 日本語 ja) for ListenScope.

Design rules:
1. Built-in English telemetry prefixes/codes (e.g., `CHORD // 01`, `SYS // CONFIG`, `AUDIO_IN`)
   stay fixed in English across all languages.
2. When language is `zh`, `ko`, or `ja`, the localized portion is rendered in Chinese, Korean,
   or Japanese respectively.
3. When language is `en`, ONLY English is shown — secondary localized suffixes are omitted or
   replaced without ever duplicating English twice.
"""

from __future__ import annotations

from typing import Optional
import re
from PySide6 import QtGui, QtWidgets

from .i18n_catalog import DYNAMIC_REGEX_RULES, EXTRA_PHRASE_MAP, HELP_TRANSLATIONS

LANGUAGES: dict[str, str] = {
    "zh": "简体中文 (ZH)",
    "en": "English (EN)",
    "ko": "한국어 (KO)",
    "ja": "日本語 (JA)",
}

DEFAULT_LANGUAGE = "zh"
_CURRENT_LANG = DEFAULT_LANGUAGE
_ZH_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def normalize_language(lang: Optional[str]) -> str:
    raw = str(lang or "").strip().lower()
    return raw if raw in LANGUAGES else DEFAULT_LANGUAGE


def get_current_language() -> str:
    return _CURRENT_LANG


def set_current_language(lang: Optional[str]) -> str:
    global _CURRENT_LANG
    _CURRENT_LANG = normalize_language(lang)
    return _CURRENT_LANG


_NAMED_TR_KEYS: dict[str, dict[str, str]] = {
    "title_workbench": {
        "zh": "音乐实时频谱 · 120s历史分轨 · 练习工作台",
        "en": "Realtime Spectrum · 120s Stem Separation · Practice Workbench",
        "ko": "실시간 스펙트럼 · 120초 스템 분리 · 연습 워크벤치",
        "ja": "リアルタイムスペクトル · 120秒ステム分離 · 練習ワークベンチ",
    },
    "tab_spectrum": {
        "zh": "实时频谱与波形",
        "en": "Spectrum · Waveform",
        "ko": "실시간 스펙트럼 · 파형",
        "ja": "スペクトル・波形",
    },
    "tab_chroma": {
        "zh": "和弦与调性",
        "en": "Chords · Key",
        "ko": "코드 · 조성 · BPM",
        "ja": "コード・調性・BPM",
    },
    "tab_mixer": {
        "zh": "分轨混音与 MIDI",
        "en": "Stem Mixer · MIDI",
        "ko": "스템 믹서 · MIDI",
        "ja": "ステム・MIDI",
    },
    "tab_resources": {
        "zh": "系统资源与日志",
        "en": "Telemetry · Logs",
        "ko": "리소스 · 로그",
        "ja": "リソース・ログ",
    },
    "tab_live": {
        "zh": "近实时分轨 [实验]",
        "en": "Live Split [EXP]",
        "ko": "준실시간 분리 [실험]",
        "ja": "準リアルタイム [実験]",
    },
    "btn_settings": {
        "zh": "设置",
        "en": "Settings",
        "ko": "설정",
        "ja": "設定",
    },
    "btn_estop": {
        "zh": "紧急停止 AI",
        "en": "E-Stop AI",
        "ko": "AI 긴급 정지",
        "ja": "AI 緊急停止",
    },
    "btn_estop_short": {
        "zh": "急停",
        "en": "E-Stop",
        "ko": "긴급 정지",
        "ja": "緊急停止",
    },
    "btn_start_capture": {
        "zh": "开始捕获",
        "en": "Start Capture",
        "ko": "캡처 시작",
        "ja": "キャプチャ開始",
    },
    "btn_stop_capture": {
        "zh": "停止捕获",
        "en": "Stop Capture",
        "ko": "캡처 중지",
        "ja": "キャプチャ停止",
    },
}


def tr(
    zh_or_key: str,
    en_or_lang: str = "",
    ko: str = "",
    ja: str = "",
    *,
    lang: str = "zh",
) -> str:
    """Return localized string for `lang` (`zh`, `en`, `ko`, `ja`).

    Supports both:
    - `tr(zh, en, ko, ja, lang=lang)`
    - `tr("named_key", lang)`
    """
    if zh_or_key in _NAMED_TR_KEYS and not ko and not ja:
        eff_lang = normalize_language(en_or_lang or lang)
        entry = _NAMED_TR_KEYS[zh_or_key]
        return entry.get(eff_lang, entry["zh"])
    code = normalize_language(lang)
    if code == "en":
        return en_or_lang or zh_or_key
    if code == "ko":
        return ko or en_or_lang or zh_or_key
    if code == "ja":
        return ja or en_or_lang or zh_or_key
    return zh_or_key


def tr_telemetry(
    en_code: str,
    arg1: str = "",
    arg2: str = "",
    arg3: str = "",
    *,
    lang: str = "zh",
    zh: str = "",
    ko: str = "",
    ja: str = "",
    en_subtitle: str = "",
    sep: str = " // ",
) -> str:
    """Format a fixed-English telemetry label with localized caption, avoiding duplicate English in `en` mode.

    Supports both:
    - `tr_telemetry("CODE", "中文", "한국어", "日本語", lang=lang)`
    - `tr_telemetry("CODE", lang, zh="中文", ko="한국어", ja="日本語")`
    """
    if arg1 in LANGUAGES and (zh or ko or ja or not arg2):
        code = normalize_language(arg1)
        zh_val, ko_val, ja_val = zh, ko, ja
    else:
        code = normalize_language(lang)
        zh_val = zh or arg1
        ko_val = ko or arg2
        ja_val = ja or arg3
    base = en_code.strip()
    if code == "en":
        sub = en_subtitle.strip()
        if not sub or sub.lower() in base.lower():
            return base
        return f"{base}{sep}{sub}"
    if code == "ko":
        return f"{base}{sep}{ko_val}" if ko_val else base
    if code == "ja":
        return f"{base}{sep}{ja_val}" if ja_val else base
    return f"{base}{sep}{zh_val}" if zh_val else base


# Exact Chinese -> {en, ko, ja} lookup table for widget tree translation
UI_PHRASE_MAP: dict[str, dict[str, str]] = {
    # Main Window Header & Tabs
    "音源:": {"en": "Source:", "ko": "오디오 소스:", "ja": "音源:"},
    "刷新音源": {"en": "Refresh", "ko": "새로고침", "ja": "更新"},
    "开始捕获": {"en": "Start Capture", "ko": "캡처 시작", "ja": "キャプチャ開始"},
    "停止捕获": {"en": "Stop Capture", "ko": "캡처 중지", "ja": "キャプチャ停止"},
    "模拟音频 (开发测试)": {"en": "Synthetic Audio (Dev Test)", "ko": "가상 오디오 (테스트)", "ja": "擬似オーディオ (テスト)"},
    "系统混音 (全部声音)": {"en": "System Loopback (All Audio)", "ko": "시스템 루프백 (전체 소리)", "ja": "システムループバック (全音声)"},
    "节拍器": {"en": "Metronome", "ko": "메트로놈", "ja": "メトロノーム"},
    "外观": {"en": "Theme", "ko": "테마", "ja": "外観"},
    "设置": {"en": "Settings", "ko": "설정", "ja": "設定"},
    "紧急停止 AI": {"en": "E-Stop AI", "ko": "AI 긴급 중지", "ja": "AI 緊急停止"},
    "捕获: 未启动": {"en": "Capture: Idle", "ko": "캡처: 대기 중", "ja": "キャプチャ: 待機中"},
    "曲目: --": {"en": "Track: --", "ko": "트랙: --", "ja": "曲目: --"},
    "调性: -- | BPM: -- | 音高: --": {
        "en": "Key: -- | BPM: -- | Pitch: --",
        "ko": "조성: -- | BPM: -- | 음고: --",
        "ja": "調性: -- | BPM: -- | ピッチ: --",
    },
    "RAM: -- | GPU VRAM: --": {
        "en": "RAM: -- | GPU VRAM: --",
        "ko": "RAM: -- | GPU VRAM: --",
        "ja": "RAM: -- | GPU VRAM: --",
    },
    "AI 任务: 空闲": {"en": "AI Job: Idle", "ko": "AI 작업: 유휴", "ja": "AI ジョブ: 待機中"},
    "// 01 实时频谱与波形": {
        "en": "// 01 Realtime Spectrum & Waveform",
        "ko": "// 01 실시간 스펙트럼 & 파형",
        "ja": "// 01 リアルタイムスペクトル＆波形",
    },
    "// 02 色度图与和弦/调性": {
        "en": "// 02 Chromagram, Chords & Key",
        "ko": "// 02 크로마그램 & 코드/조성",
        "ja": "// 02 クロマグラム＆コード/調性",
    },
    "// 03 AI 分轨与练耳工作台": {
        "en": "// 03 AI Stem & Ear-Training Workstation",
        "ko": "// 03 AI 스템 분리 & 청음 워크스테이션",
        "ja": "// 03 AI ステム分離＆耳コピワークステーション",
    },
    "// 04 系统资源与日志": {
        "en": "// 04 System Resources & Logs",
        "ko": "// 04 시스템 리소스 & 로그",
        "ja": "// 04 システムリソース＆ログ",
    },
    "// 05 实验性低延迟分离": {
        "en": "// 05 Experimental Low-Latency Separation",
        "ko": "// 05 실험적 저지연 스템 분리",
        "ja": "// 05 実験的低遅延ステム分離",
    },
    # 120s History Dock
    "120 秒历史波形回溯 & A/B 循环区间选择 (拖拽高亮区域设定 A/B)": {
        "en": "120s History Waveform & A/B Loop Selector (Drag region to set A/B)",
        "ko": "120초 히스토리 파형 & A/B 루프 구간 선택 (드래그하여 A/B 설정)",
        "ja": "120秒履歴波形＆A/Bループ区間選択 (ドラッグでA/B設定)",
    },
    "倒退:": {"en": "Rollback:", "ko": "되감기:", "ja": "巻き戻し:"},
    "至倒退": {"en": "To -", "ko": "끝 -", "ja": "終了 -"},
    "倒退": {"en": "From -", "ko": "시작 -", "ja": "開始 -"},
    "放大": {"en": "Zoom In", "ko": "확대", "ja": "拡大"},
    "缩小": {"en": "Zoom Out", "ko": "축소", "ja": "縮小"},
    "全景": {"en": "Full 120s", "ko": "전체 보기", "ja": "全体表示"},
    "A/B 循环播放": {"en": "A/B Loop Play", "ko": "A/B 루프 재생", "ja": "A/B ループ再生"},
    "保存当前段落为书签": {"en": "Save Bookmark", "ko": "북마크 저장", "ja": "ブックマーク保存"},
    "书签:": {"en": "Bookmarks:", "ko": "북마크:", "ja": "ブックマーク:"},
    "加载书签": {"en": "Load", "ko": "불러오기", "ja": "読込"},
    "删除书签": {"en": "Delete", "ko": "삭제", "ja": "削除"},
    "导出选中片段 WAV": {"en": "Export Selection WAV", "ko": "선택 구간 WAV 내보내기", "ja": "選択区間 WAV 書き出し"},
    "倍速:": {"en": "Speed:", "ko": "배속:", "ja": "再生速度:"},
    "2-Stem 快速分轨 (人声/伴奏)": {
        "en": "2-Stem Fast Split (Vocals/Inst)",
        "ko": "2-Stem 빠른 분리 (보컬/반주)",
        "ja": "2-Stem 高速分離 (ボーカル/伴奏)",
    },
    "4-Stem 精细分轨 (人声/鼓/贝斯/其他)": {
        "en": "4-Stem Deep Split (Vocals/Drums/Bass/Other)",
        "ko": "4-Stem 정밀 분리 (보컬/드럼/베이스/기타)",
        "ja": "4-Stem 精密分離 (ボーカル/ドラム/ベース/その他)",
    },
    "取消当前 AI 任务": {"en": "Cancel AI Job", "ko": "AI 작업 취소", "ja": "AI ジョブ中止"},
    # Spectrum Widget
    "实时频谱与音高监测": {
        "en": "Realtime Spectrum & Pitch Monitor",
        "ko": "실시간 스펙트럼 & 음고 모니터",
        "ja": "リアルタイムスペクトル＆ピッチ監視",
    },
    "捕获音频流的时域包络、FFT 与对数频谱": {
        "en": "Time-domain envelope, FFT, and logarithmic frequency spectrum",
        "ko": "오디오 스트림의 시간 영역 엔벨로프, FFT 및 로그 스펙트럼",
        "ja": "音声ストリームの時間領域エンベロープ、FFT、対数スペクトル",
    },
    "视图": {"en": "View", "ko": "뷰 레이아웃", "ja": "表示切替"},
    "双联总览": {"en": "Dual Monitor", "ko": "듀얼 모니터", "ja": "デュアル表示"},
    "频谱专注": {"en": "Frequency Focus", "ko": "주파수 집중", "ja": "スペクトル優先"},
    "时序专注": {"en": "Time-Series Focus", "ko": "시계열 집중", "ja": "時系列優先"},
    "单列巡检": {"en": "Single-Column Stack", "ko": "단일 열 스택", "ja": "1列スタック"},
    "主音高 / 基频": {"en": "Fundamental Pitch / F0", "ko": "기본 음고 / F0", "ja": "基本ピッチ / F0"},
    "等待有效音高": {"en": "Waiting for pitch...", "ko": "유효 음고 대기 중", "ja": "有効なピッチ待機中"},
    "RMS 均方根电平": {"en": "RMS Level", "ko": "RMS 평균 레벨", "ja": "RMS 実効レベル"},
    "静音输入将保持低电平": {"en": "Silent input stays low", "ko": "무음 입력 시 낮은 레벨 유지", "ja": "無音時は低レベルを維持"},
    "Peak 峰值电平": {"en": "Peak Level", "ko": "Peak 피크 레벨", "ja": "Peak ピークレベル"},
    "接近 0 dBFS 时注意削波": {"en": "Watch clipping near 0 dBFS", "ko": "0 dBFS 근처 클리핑 주의", "ja": "0 dBFS 付近のクリップに注意"},
    "分析窗口 / 环形缓冲": {"en": "Analysis Window / Ring Buffer", "ko": "분석 윈도우 / 링 버퍼", "ja": "解析窓 / リングバッファ"},
    "实时波形包络": {"en": "Realtime Waveform Envelope", "ko": "실시간 파형 엔벨로프", "ja": "リアルタイム波形エンベロープ"},
    "峰值与包络动态": {"en": "Peak & envelope dynamics", "ko": "피크 및 엔벨로프 다이내믹스", "ja": "ピークとエンベロープ動態"},
    "FFT 线性频谱": {"en": "FFT Linear Spectrum", "ko": "FFT 선형 스펙트럼", "ja": "FFT 線形スペクトル"},
    "0 - 12 kHz 细节能量分布": {"en": "0 - 12 kHz energy distribution", "ko": "0 - 12 kHz 에너지 분포", "ja": "0 - 12 kHz エネルギー分布"},
    "对数频率能量分布": {"en": "Log-Frequency Energy", "ko": "로그 주파수 에너지 분포", "ja": "対数周波数エネルギー分布"},
    "31.5 Hz - 16 kHz 听感频段": {"en": "31.5 Hz - 16 kHz perceptual bands", "ko": "31.5 Hz - 16 kHz 청감 대역", "ja": "31.5 Hz - 16 kHz 聴感帯域"},
    "滚动频谱瀑布图": {"en": "Scrolling Spectrogram Waterfall", "ko": "스크롤 스펙트로그램 폭포수", "ja": "スクロール・スペクトログラム"},
    "最近约 6 秒时频轨迹": {"en": "Recent ~6s time-frequency trace", "ko": "최근 약 6초 시간-주파수 궤적", "ja": "直近約6秒の時間周波数軌跡"},
    # Chroma & Harmony Widget
    "当前和弦推测": {"en": "Current Chord Estimate", "ko": "현재 코드 추정", "ja": "現在のコード推定"},
    "全局调性": {"en": "Global Key", "ko": "전역 조성", "ja": "全体の調性"},
    "BPM 速度与基频": {"en": "BPM Tempo & Pitch", "ko": "BPM 템포 & 기본 주파수", "ja": "BPM テンポ＆基本周波数"},
    "和弦练习": {"en": "Chord Practice", "ko": "코드 연습", "ja": "コード練習"},
    "等待音频": {"en": "Waiting for audio", "ko": "오디오 대기 중", "ja": "音声待機中"},
    "置信度: --": {"en": "Confidence: --", "ko": "신뢰도: --", "ja": "信頼度: --"},
    "调内级数: --": {"en": "Roman Degree: --", "ko": "로마 숫자 도수: --", "ja": "ローマ数字度数: --"},
    "关系调: --": {"en": "Relative Key: --", "ko": "관계조: --", "ja": "関係調: --"},
    "检测窗口: ~15-30s": {"en": "Window: ~15-30s", "ko": "감지 윈도우: ~15-30s", "ja": "検出窓: ~15-30s"},
    "音高: -- Hz": {"en": "Pitch: -- Hz", "ko": "음고: -- Hz", "ja": "ピッチ: -- Hz"},
    "音分偏差: -- (绿<=5c / 黄<=20c / 红>20c)": {
        "en": "Cents Deviation: -- (Green<=5c / Amber<=20c / Red>20c)",
        "ko": "센트 편차: -- (초록<=5c / 노랑<=20c / 빨강>20c)",
        "ja": "セント偏差: -- (緑<=5c / 黄<=20c / 赤>20c)",
    },
    "曲目跟踪: 等待信号 / Windows SMTC": {
        "en": "Track Monitor: Waiting for signal / Windows SMTC",
        "ko": "트랙 모니터: 신호 대기 중 / Windows SMTC",
        "ja": "曲目追跡: 信号待機中 / Windows SMTC",
    },
    "SMTC 曲目监测: 待启动": {
        "en": "SMTC Monitor: Standby",
        "ko": "SMTC 모니터: 대기 중",
        "ja": "SMTC監視: 待機中",
    },
    "关闭按钮行为:": {"en": "Close Button:", "ko": "닫기 버튼 동작:", "ja": "閉じるボタン:"},
    "每次询问": {"en": "Ask Every Time", "ko": "매번 묻기", "ja": "毎回確認"},
    "最小化到托盘": {"en": "Minimize to Tray", "ko": "트레이로 최소화", "ja": "トレイに最小化"},
    "退出程序": {"en": "Quit Application", "ko": "프로그램 종료", "ja": "アプリを終了"},
    "记住我的选择": {"en": "Remember my choice", "ko": "선택 기억", "ja": "選択を記憶する"},
    "关闭 ListenScope": {"en": "Close ListenScope", "ko": "ListenScope 닫기", "ja": "ListenScope を閉じる"},
    "点击关闭按钮时希望执行什么操作？": {
        "en": "What should happen when you click the close button?",
        "ko": "닫기 버튼을 클릭할 때 어떤 작업을 수행할까요?",
        "ja": "閉じるボタンをクリックしたときの動作を選択してください。",
    },
    "自动增益": {"en": "Auto Gain", "ko": "자동 게인", "ja": "オートゲイン"},
    "固定 ±1": {"en": "Fixed ±1", "ko": "고정 ±1", "ja": "固定 ±1"},
    "切换波形自动增益与固定 ±1 振幅范围": {
        "en": "Toggle waveform auto-gain vs fixed ±1 range",
        "ko": "파형 자동 게인 / 고정 ±1 범위 전환",
        "ja": "波形のオートゲインと固定 ±1 範囲を切り替え",
    },
    "换歌重置和弦/调性": {"en": "Reset on Track Change", "ko": "곡 변경 시 리셋", "ja": "曲変更時にリセット"},
    "手动重置": {"en": "Manual Reset", "ko": "수동 리셋", "ja": "手動リセット"},
    "移调 / 变调夹:": {"en": "Transpose / Capo:", "ko": "조옮김 / 카포:", "ja": "移調 / カポ:"},
    "原调 (0 半音 / Capo 0)": {"en": "Original Key (0 st / Capo 0)", "ko": "원키 (0 반음 / Capo 0)", "ja": "原調 (0 半音 / Capo 0)"},
    "走向显示:": {"en": "Progression Display:", "ko": "진행 표시:", "ja": "進行表示:"},
    "仅显示和弦名 (C → G → Am)": {
        "en": "Chord Names Only (C → G → Am)",
        "ko": "코드명만 표시 (C → G → Am)",
        "ja": "コード名のみ (C → G → Am)",
    },
    "仅显示罗马级数 (I → V → vi)": {
        "en": "Roman Degrees Only (I → V → vi)",
        "ko": "로마 도수만 표시 (I → V → vi)",
        "ja": "ローマ数字度数のみ (I → V → vi)",
    },
    "同时显示和弦与级数": {
        "en": "Both Chord & Degree",
        "ko": "코드명과 도수 함께 표시",
        "ja": "コード名と度数を同時表示",
    },
    "清空走向": {"en": "Clear Progression", "ko": "진행 초기화", "ja": "進行クリア"},
    "实时 12 音级色度能量分布 (Chromagram)": {
        "en": "Realtime 12-Pitch-Class Chromagram",
        "ko": "실시간 12음계 크로마 에너지 분포 (Chromagram)",
        "ja": "リアルタイム12音階クロマ分布 (Chromagram)",
    },
    "滚动色度时间热力图 (Chroma History)": {
        "en": "Scrolling Chroma History Heatmap",
        "ko": "스크롤 크로마 히스토리 히트맵",
        "ja": "スクロール・クロマ履歴ヒートマップ",
    },
    # Mixer Widget
    "多轨混音与伴奏练耳台 (AI 分轨完成后激活)": {
        "en": "Multi-Stem Mixer & Ear-Training Desk (Active after AI separation)",
        "ko": "멀티 스템 믹서 & 청음 데스크 (AI 분리 완료 후 활성화)",
        "ja": "マルチステムミキサー＆耳コピ卓 (AI分離完了後に有効化)",
    },
    "播放混音": {"en": "Play Mix", "ko": "믹스 재생", "ja": "ミックス再生"},
    "暂停": {"en": "Pause", "ko": "일시정지", "ja": "一時停止"},
    "停止/回零": {"en": "Stop / Rewind", "ko": "정지/처음으로", "ja": "停止/先頭へ"},
    "从 A 点重播": {"en": "Replay from A", "ko": "A 지점부터 재생", "ja": "A点から再生"},
    "A-B 循环": {"en": "A-B Loop", "ko": "A-B 루프", "ja": "A-B ループ"},
    "设当前为 A": {"en": "Set A Here", "ko": "현재 위치를 A로", "ja": "現在位置をAに設定"},
    "设当前为 B": {"en": "Set B Here", "ko": "현재 위치를 B로", "ja": "現在位置をBに設定"},
    "重置全段 A/B": {"en": "Reset Full A/B", "ko": "전체 구간 리셋", "ja": "全区間A/Bリセット"},
    "导出当前混音 WAV": {"en": "Export Current Mix WAV", "ko": "현재 믹스 WAV 내보내기", "ja": "現在のミックスをWAV出力"},
    "导出扒谱练习单 (.md)": {"en": "Export Practice Sheet (.md)", "ko": "채보 연습 시트 내보내기 (.md)", "ja": "耳コピ練習シート出力 (.md)"},
    "监听:": {"en": "Monitor:", "ko": "모니터:", "ja": "モニター:"},
    "全部": {"en": "All Stems", "ko": "전체", "ja": "全トラック"},
    "纯伴奏 (去人声)": {"en": "Instrumental (No Vocals)", "ko": "반주만 (보컬 제외)", "ja": "伴奏のみ (ボーカル消去)"},
    "仅人声": {"en": "Vocals Only", "ko": "보컬만", "ja": "ボーカルのみ"},
    "仅贝斯": {"en": "Bass Only", "ko": "베이스만", "ja": "ベースのみ"},
    "仅鼓组": {"en": "Drums Only", "ko": "드럼만", "ja": "ドラムのみ"},
    "仅其他": {"en": "Other Only", "ko": "기타 악기만", "ja": "その他のみ"},
    "贝斯独听 +12 dB": {"en": "Bass Solo Boost", "ko": "베이스 솔로 부스트", "ja": "ベース独聴ブースト"},
    "导出含独听增益": {"en": "Apply Boost to Export", "ko": "내보내기에 부스트 적용", "ja": "書き出しにブースト適用"},
    "人声 (Vocals)": {"en": "Vocals", "ko": "보컬 (Vocals)", "ja": "ボーカル (Vocals)"},
    "伴奏 (Instrumental)": {"en": "Instrumental", "ko": "반주 (Instrumental)", "ja": "伴奏 (Instrumental)"},
    "鼓组 (Drums)": {"en": "Drums", "ko": "드럼 (Drums)", "ja": "ドラム (Drums)"},
    "贝斯 (Bass)": {"en": "Bass", "ko": "베이스 (Bass)", "ja": "ベース (Bass)"},
    "其他乐器 (Other)": {"en": "Other Instruments", "ko": "기타 악기 (Other)", "ja": "その他楽器 (Other)"},
    "导出轨道": {"en": "Export Stem", "ko": "트랙 내보내기", "ja": "トラック出力"},
    "转 MIDI": {"en": "To MIDI", "ko": "MIDI 변환", "ja": "MIDI変換"},
    "导入音频文件直接分轨 / 转 MIDI": {
        "en": "Import Local Audio File for Separation / MIDI",
        "ko": "로컬 오디오 파일 불러오기 (분리 / MIDI 변환)",
        "ja": "音声ファイルを読み込んで分離 / MIDI変換",
    },
    "导入音频并 2-Stem 分轨": {"en": "Import && 2-Stem Split", "ko": "불러오기 및 2-Stem 분리", "ja": "読み込んで 2-Stem 分離"},
    "导入音频并 4-Stem 分轨": {"en": "Import && 4-Stem Split", "ko": "불러오기 및 4-Stem 분리", "ja": "読み込んで 4-Stem 分離"},
    "导入单轨音频直接转 MIDI": {"en": "Import Audio Directly to MIDI", "ko": "단일 트랙 바로 MIDI 변환", "ja": "単一音声を直接 MIDI 変換"},
    "导入音频直接深度分析": {"en": "Import Audio for Deep Analysis", "ko": "오디오 심층 분석 실행", "ja": "音声を読み込んで詳細解析"},
    "和弦时间轴 & 贝斯根音": {"en": "Chord Timeline & Bass Root", "ko": "코드 타임라인 & 베이스 근음", "ja": "コード進行＆ベースルート音"},
    "鼓组 16 步节奏格": {"en": "16-Step Drum Grid", "ko": "드럼 16스텝 리듬 그리드", "ja": "ドラム16ステップグリッド"},
    "MIDI 钢琴卷帘 (Basic Pitch)": {"en": "MIDI Piano Roll (Basic Pitch)", "ko": "MIDI 피아노 롤 (Basic Pitch)", "ja": "MIDI ピアノロール (Basic Pitch)"},
    "试听鼓点节奏": {"en": "Audition Drum Pattern", "ko": "드럼 리듬 미리듣기", "ja": "ドラムパターン試聴"},
    "保存修正后 MIDI...": {"en": "Save Edited MIDI...", "ko": "편집된 MIDI 저장...", "ja": "編集済み MIDI を保存..."},
    # Resource Widget
    "硬件、显存与子进程资源实时看门狗": {
        "en": "Hardware, VRAM & Subprocess Resource Watchdog",
        "ko": "하드웨어, VRAM & 서브프로세스 리소스 워치독",
        "ja": "ハードウェア・VRAM・サブプロセス監視",
    },
    "系统与硬件自检信息": {"en": "System & Hardware Self-Test Summary", "ko": "시스템 & 하드웨어 자가진단 요약", "ja": "システム＆ハードウェア自己診断"},
    "诊断日志与性能快照": {"en": "Diagnostic Logs & Performance Snapshots", "ko": "진단 로그 & 성능 스냅샷", "ja": "診断ログ＆パフォーマンススナップショット"},
    "导出诊断包 (.zip)": {"en": "Export Diagnostic Bundle (.zip)", "ko": "진단 패키지 내보내기 (.zip)", "ja": "診断パッケージ出力 (.zip)"},
    # Appearance Dialog
    "主题外观与字体": {"en": "Theme Appearance & Typography", "ko": "테마 외관 & 글꼴 설정", "ja": "テーマ外観＆フォント設定"},
    "实时预览主题预设、明暗模式、本机字体与字号，点击“保存更改”即可持久化": {
        "en": "Live preview theme presets, light/dark mode, local fonts & sizes; click Save to persist",
        "ko": "테마 프리셋, 라이트/다크 모드, 로컬 글꼴 및 크기를 실시간 미리보기 후 저장",
        "ja": "テーマプリセット、明暗モード、フォントとサイズをリアルタイムプレビューして保存",
    },
    "经典暗夜": {"en": "Classic Dark", "ko": "클래식 다크", "ja": "クラシック"},
    "酸性遥测": {"en": "Acid Telemetry", "ko": "애시드 텔레메트리", "ja": "アシッド・テレメトリ"},
    "夜间 (Dark)": {"en": "Dark Mode", "ko": "다크 모드 (Dark)", "ja": "ダーク (Dark)"},
    "白天 (Light)": {"en": "Light Mode", "ko": "라이트 모드 (Light)", "ja": "ライト (Light)"},
    "跟随系统": {"en": "Follow System", "ko": "시스템 설정 따름", "ja": "システム連動"},
    "黑夜 / 白天 / 跟随系统": {"en": "Dark / Light / Follow System", "ko": "다크 / 라이트 / 시스템 연동", "ja": "ダーク / ライト / システム連動"},
    "界面语言": {"en": "Interface Language", "ko": "인터페이스 언어", "ja": "表示言語"},
    "电脑已安装字体": {"en": "Installed System Font", "ko": "시스템 설치 글꼴", "ja": "インストール済みフォント"},
    "重新扫描字体": {"en": "Rescan Fonts", "ko": "글꼴 다시 스캔", "ja": "フォント再スキャン"},
    "全局字体大小": {"en": "Global Font Size", "ko": "전역 글꼴 크기", "ja": "全体フォントサイズ"},
    "恢复默认外观": {"en": "Restore Defaults", "ko": "기본값 복원", "ja": "デフォルトに戻す"},
    "取消": {"en": "Cancel", "ko": "취소", "ja": "キャンセル"},
    "保存更改": {"en": "Save Changes", "ko": "변경사항 저장", "ja": "変更を保存"},
    "无边框圆角窗口 (推荐)": {
        "en": "Frameless Rounded Window (Recommended)",
        "ko": "프레임리스 둥근 창 (권장)",
        "ja": "フレームレス角丸ウィンドウ (推奨)",
    },
    "自定义背景图": {"en": "Custom Wallpaper", "ko": "사용자 지정 배경 이미지", "ja": "カスタム背景画像"},
    "选择背景图…": {"en": "Choose Image...", "ko": "배경 이미지 선택...", "ja": "背景画像を選択..."},
    "清除背景图": {"en": "Clear Image", "ko": "배경 지우기", "ja": "背景をクリア"},
    # Settings Dialog
    "设置中心": {"en": "Settings Center", "ko": "설정 센터", "ja": "設定センター"},
    "恢复本页默认": {"en": "Reset This Page", "ko": "현재 페이지 기본값 복원", "ja": "このページを初期化"},
    "保存设置": {"en": "Save Settings", "ko": "설정 저장", "ja": "設定を保存"},
    "主题与外观": {"en": "Appearance & About", "ko": "테마 & 정보", "ja": "外観＆プロジェクト情報"},
    "资源与保护": {"en": "Resource Guardrails", "ko": "리소스 보호 임계값", "ja": "リソース保護設定"},
    "AI 与 MIDI 环境": {"en": "AI & MIDI Runtimes", "ko": "AI & MIDI 런타임 환경", "ja": "AI ＆ MIDI 実行環境"},
    "系统诊断": {"en": "System Diagnostics", "ko": "시스템 진단", "ja": "システム診断"},
    # Exact button & label strings from MainWindow, Spectrum, Chroma, Mixer
    "刷新进程": {"en": "Refresh", "ko": "프로세스 새로고침", "ja": "プロセス更新"},
    "未捕获": {"en": "Idle", "ko": "미캡처", "ja": "未キャプチャ"},
    "实时频谱与波形分析": {"en": "Realtime Spectrum & Waveform Analysis", "ko": "실시간 스펙트럼 & 파형 분석", "ja": "リアルタイムスペクトル＆波形解析"},
    "实时监听": {"en": "Live Monitor", "ko": "실시간 모니터", "ja": "リアルタイム監視"},
    "频率诊断": {"en": "Frequency Diag", "ko": "주파수 진단", "ja": "周波数診断"},
    "时频追踪": {"en": "Time-Freq Trace", "ko": "시간-주파수 추적", "ja": "時間周波数追跡"},
    "和弦推测": {"en": "Chord Estimate", "ko": "코드 추정", "ja": "コード推定"},
    "调性推测": {"en": "Key Estimate", "ko": "조성 추정", "ja": "調性推定"},
    "节拍 · 音高 · CPU 节拍器": {"en": "Tempo · Pitch · CPU Metronome", "ko": "템포 · 음고 · CPU 메트로놈", "ja": "テンポ・ピッチ・CPUメトロノーム"},
    "Tap 定速": {"en": "Tap Tempo", "ko": "Tap 템포", "ja": "Tap テンポ"},
    "同步检测BPM": {"en": "Sync BPM", "ko": "감지 BPM 동기화", "ja": "検出BPM同期"},
    "随播节拍器": {"en": "Overlay Click", "ko": "재생 시 메트로놈", "ja": "再生連動メトロノーム"},
    "预备拍 (1小节)": {"en": "Count-In (1 Bar)", "ko": "예비박 (1마디)", "ja": "カウントイン (1小節)"},
    "独立节拍器": {"en": "Standalone Click", "ko": "독립 메트로놈", "ja": "単独メトロノーム"},
    "和弦名": {"en": "Chords", "ko": "코드명", "ja": "コード名"},
    "罗马数字": {"en": "Degrees", "ko": "로마 도수", "ja": "ローマ数字"},
    "和弦名与级数": {"en": "Chord & Degree", "ko": "코드명 + 도수", "ja": "コード名と度数"},
    "移调/Capo:": {"en": "Transpose/Capo:", "ko": "조옮김/Capo:", "ja": "移調/Capo:"},
    "自动切歌重置": {"en": "Auto Track Reset", "ko": "곡 변경 자동 리셋", "ja": "曲変更自動リセット"},
    "12-BIN CHROMA // 实时色度分布": {"en": "12-BIN CHROMA", "ko": "12-BIN CHROMA // 실시간 크로마 분포", "ja": "12-BIN CHROMA // リアルタイムクロマ分布"},
    "CHROMA HEATMAP // 有界时序热图 (30s)": {"en": "CHROMA HEATMAP (30S)", "ko": "CHROMA HEATMAP // 시계열 히트맵 (30s)", "ja": "CHROMA HEATMAP // 時系列ヒートマップ (30s)"},
    "选最近 10s": {"en": "Last 10s", "ko": "최근 10초", "ja": "直近 10秒"},
    "选最近 30s": {"en": "Last 30s", "ko": "최근 30초", "ja": "直近 30秒"},
    "选最近 60s": {"en": "Last 60s", "ko": "최근 60초", "ja": "直近 60秒"},
    "设定 A/B 区间": {"en": "Set A/B Range", "ko": "A/B 구간 설정", "ja": "A/B 区間設定"},
    "120 秒总览": {"en": "Full 120s", "ko": "120초 전체", "ja": "120秒全体"},
    "A/B 播放": {"en": "A/B Play", "ko": "A/B 재생", "ja": "A/B 再生"},
    "停止回放": {"en": "Stop", "ko": "재생 중지", "ja": "再生停止"},
    "贴近零点": {"en": "Zero-Cross", "ko": "제로크로스 스냅", "ja": "ゼロクロス補正"},
    "A/B 循环": {"en": "A/B Loop", "ko": "A/B 루프", "ja": "A/B ループ"},
    "导出 A/B 片段 WAV": {"en": "Export A/B WAV", "ko": "A/B 구간 WAV 내보내기", "ja": "A/B 区間 WAV 出力"},
    "导入本地音频(<=120s)": {"en": "Import Audio (<=120s)", "ko": "로컬 오디오 불러오기(<=120s)", "ja": "音声ファイル読込(<=120s)"},
    "A/B 书签(<=12):": {"en": "Bookmarks (<=12):", "ko": "A/B 북마크(<=12):", "ja": "A/B ブックマーク(<=12):"},
    "保存当前 A/B": {"en": "Save A/B", "ko": "현재 A/B 저장", "ja": "現在のA/Bを保存"},
    "跳转此书签": {"en": "Jump", "ko": "북마크 이동", "ja": "ジャンプ"},
    "2-Stem 模型:": {"en": "2-Stem Model:", "ko": "2-Stem 모델:", "ja": "2-Stem モデル:"},
    "优先 GPU (未就绪)": {"en": "Prefer GPU (Not Ready)", "ko": "GPU 우선 (미준비)", "ja": "GPU 優先 (未準備)"},
    "优先 GPU (已就绪)": {"en": "Prefer GPU (Ready)", "ko": "GPU 우선 (준비됨)", "ja": "GPU 優先 (準備完了)"},
    "AI 2-Stem 分轨 (人声/伴奏)": {"en": "AI 2-Stem Split (Vocals/Inst)", "ko": "AI 2-Stem 분리 (보컬/반주)", "ja": "AI 2-Stem 分離 (ボーカル/伴奏)"},
    "AI 4-Stem 分轨 (HTDemucs)": {"en": "AI 4-Stem Split (HTDemucs)", "ko": "AI 4-Stem 분리 (HTDemucs)", "ja": "AI 4-Stem 分離 (HTDemucs)"},
    "分轨混音 · 深度扒谱 · MIDI 转录": {"en": "Stem Mixer · Deep Analysis · MIDI Transcription", "ko": "스템 믹서 · 심층 채보 · MIDI 변환", "ja": "ステムミキサー・詳細耳コピ・MIDI転写"},
    "播放分轨": {"en": "Play Stems", "ko": "스템 재생", "ja": "ステム再生"},
    "停止": {"en": "Stop", "ko": "정지", "ja": "停止"},
    "循环": {"en": "Loop", "ko": "루프", "ja": "ループ"},
    "导出混合 WAV": {"en": "Export Mix WAV", "ko": "믹스 WAV 내보내기", "ja": "ミックス WAV 出力"},
    "清除分轨结果": {"en": "Clear Stems", "ko": "분리 결과 지우기", "ja": "分離結果クリア"},
    "监听": {"en": "Monitor", "ko": "모니터", "ja": "モニター"},
    "纯伴奏": {"en": "Inst Only", "ko": "반주만", "ja": "伴奏のみ"},
    "⚠️ 高增益护耳警告": {"en": "⚠️ High Gain Hearing Warning", "ko": "⚠️ 고게인 청력 보호 경고", "ja": "⚠️ 高ゲイン聴覚保護警告"},
    "不变调倍速:": {"en": "Time-Stretch:", "ko": "음고유지 배속:", "ja": "ピッチ維持倍速:"},
    "循环选中和弦段": {"en": "Loop Selected Chord", "ko": "선택 코드 구간 루프", "ja": "選択コード区間ループ"},
    "取消局部循环": {"en": "Clear Sub-Loop", "ko": "구간 루프 해제", "ja": "部分ループ解除"},
    "进度:": {"en": "Progress:", "ko": "진행:", "ja": "進行:"},
    "载入实时视图": {"en": "To Live View", "ko": "실시간 뷰로 로드", "ja": "リアルタイム表示へ"},
    "打开单轨 WAV...": {"en": "Open Stem WAV...", "ko": "단일 WAV 열기...", "ja": "単一 WAV を開く..."},
    "MIDI 环境设置": {"en": "MIDI Setup", "ko": "MIDI 환경 설정", "ja": "MIDI 環境設定"},
    "另存 MIDI (.mid)": {"en": "Save MIDI (.mid)", "ko": "MIDI 다른 이름 저장 (.mid)", "ja": "MIDI 別名保存 (.mid)"},
    "分析和弦与节奏": {"en": "Analyze Chords && Rhythm", "ko": "코드 && 리듬 분석", "ja": "コード＆リズム解析"},
    "导出扒谱表 (.md/.csv)": {"en": "Export Sheet (.md/.csv)", "ko": "채보 시트 내보내기 (.md/.csv)", "ja": "耳コピ表出力 (.md/.csv)"},
    "取消任务": {"en": "Cancel Job", "ko": "작업 취소", "ja": "ジョブ中止"},
    # UX Polish, Animations, Surface Styles, Tray, Bootstrap Progress & Logs
    "极简流光框 (推荐)": {"en": "Minimal Glow Rim (Recommended)", "ko": "미니멀 글로우 림 (권장)", "ja": "ミニマル発光リム (推奨)"},
    "精密四角卡标": {"en": "Corner Brackets", "ko": "코너 브래킷", "ja": "精密コーナーブラケット"},
    "底部高亮轨": {"en": "Bottom Highlight Rail", "ko": "하단 하이라이트 레일", "ja": "ボトムハイライトレール"},
    "微立体质感边缘 (推荐)": {"en": "Subtle Tactile Edge (Recommended)", "ko": "입체 미세 질감 (권장)", "ja": "微立体リムエッジ (推奨)"},
    "极简平面锐利": {"en": "Crisp Flat Edge", "ko": "플랫 샤프 엣지", "ja": "フラットシャープ"},
    "硬朗机械棱边": {"en": "Hard Mechanical Bevel", "ko": "하드 메카니컬 베벨", "ja": "ハードメカニカルベベル"},
    "交互与聚焦": {"en": "Interaction & Focus", "ko": "상호작용 및 포커스", "ja": "操作とフォーカス"},
    "交互与聚焦:": {"en": "Interaction & Focus:", "ko": "상호작용 및 포커스:", "ja": "操作とフォーカス:"},
    "质感与托盘": {"en": "Finish & Tray", "ko": "질감 및 트레이", "ja": "質感とトレイ"},
    "质感与托盘:": {"en": "Finish & Tray:", "ko": "질감 및 트레이:", "ja": "質感とトレイ:"},
    "遥测微动画": {"en": "Telemetry Animations", "ko": "텔레메트리 애니메이션", "ja": "テレメトリ演出"},
    "遥测微动画:": {"en": "Telemetry Animations:", "ko": "텔레메트리 애니메이션:", "ja": "テレメトリ演出:"},
    "点击右上角 × 时最小化到系统托盘": {
        "en": "Minimize to tray on close (×)",
        "ko": "닫기(×) 클릭 시 시스템 트레이로 최소화",
        "ja": "×ボタン押下時にシステムトレイへ最小化",
    },
    "随音乐高潮动态变化": {
        "en": "React to music dynamics & climax",
        "ko": "음악 에너지·클라이맥스 연동",
        "ja": "楽曲の音量・盛り上がりに連動",
    },
    "遥测动画随音乐实时响应": {
        "en": "React to music dynamics & climax",
        "ko": "음악 에너지·클라이맥스 연동",
        "ja": "楽曲の音量・盛り上がりに連動",
    },
    "打开日志目录": {"en": "Open Logs Folder", "ko": "로그 폴더 열기", "ja": "ログフォルダを開く"},
    "前往 AI 与 MIDI 环境 →": {"en": "Go to AI & MIDI Setup →", "ko": "AI & MIDI 환경으로 이동 →", "ja": "AI・MIDI環境へ進む →"},
    "取消安装": {"en": "Cancel Setup", "ko": "설치 취소", "ja": "導入中止"},
    "立即重启 ListenScope 生效": {
        "en": "Restart ListenScope Now",
        "ko": "지금 ListenScope 다시 시작",
        "ja": "今すぐ ListenScope を再起動",
    },
    "重启失败，请手动重新打开": {
        "en": "Restart failed. Please reopen ListenScope manually.",
        "ko": "다시 시작하지 못했습니다. ListenScope를 수동으로 다시 열어 주세요.",
        "ja": "再起動に失敗しました。手動で ListenScope を開き直してください。",
    },
    "待命：支持多源下载，低速或断流时自动切换高速镜像": {
        "en": "Standby: multi-mirror download enabled with automatic slow-mirror failover",
        "ko": "대기 중: 다중 미러 및 저속/끊김 시 자동 미러 전환 지원",
        "ja": "待機中: マルチミラー対応・低速時は高速ミラーへ自動切替",
    },
    "准备就绪：点击「扫描本机 PyTorch 环境」自动查找电脑已安装的 PyTorch；若未安装可点击「一键自动配置 AI + MIDI」在同级目录自动配置（切换页面不会中断）。": {
        "en": "Ready: Scan local PyTorch installations or click 'One-Click AI + MIDI Setup' to auto-configure beside the app (continues safely if you switch pages).",
        "ko": "준비됨: 로컬 PyTorch 환경을 스캔하거나 '원클릭 AI + MIDI 설정'으로 앱 폴더에 자동 구성하세요(페이지 이동 시에도 중단되지 않음).",
        "ja": "準備完了: 「ローカル PyTorch 検出」または「AI + MIDI 一括構築」でアプリ同階層へ自動構築します（画面切替でも中断されません）。",
    },
    "准备就绪：点击「扫描本机 PyTorch 环境」自动查找电脑已安装的 PyTorch；若未安装可点击「一键自动配置 AI + MIDI」在同级目录自动下载配置（切换页面不会中断）。": {
        "en": "Ready: Scan local PyTorch installations or click 'One-Click AI + MIDI Setup' to auto-download & configure beside the app (continues safely if you switch pages).",
        "ko": "준비됨: 로컬 PyTorch 환경을 스캔하거나 '원클릭 AI + MIDI 설정'으로 앱 폴더에 자동 다운로드 및 구성하세요(페이지 이동 시에도 중단되지 않음).",
        "ja": "準備完了: 「ローカル PyTorch 検出」または「AI + MIDI 一括構築」でアプリ同階層へ自動ダウンロード・構築します（画面切替でも中断されません）。",
    },
    "一键环境初始化进度与镜像切换日志将显示在这里...": {
        "en": "Turnkey setup progress and mirror-switch logs will appear here...",
        "ko": "원클릭 환경 구성 진행 상황 및 미러 전환 로그가 여기에 표시됩니다...",
        "ja": "環境セットアップの進捗とミラー切替ログがここに表示されます...",
    },
    "显示主界面": {"en": "Show ListenScope", "ko": "창 보이기", "ja": "メイン画面を表示"},
    "打开设置": {"en": "Open Settings", "ko": "설정 열기", "ja": "設定を開く"},
    "退出 ListenScope": {"en": "Quit ListenScope", "ko": "ListenScope 종료", "ja": "ListenScope を終了"},
    "[OK] 环境配置与验证全部完成（GPU AI 已就绪），点下方「保存设置」即可立即开始分轨！": {
        "en": "[OK] Environment setup and verification succeeded (GPU AI Ready). Click Save below to start!",
        "ko": "[OK] 환경 구성 및 검증 완료(GPU AI 준비됨). 아래 저장을 누르면 바로 사용할 수 있습니다!",
        "ja": "[OK] 環境構築と検証が完了しました（GPU AI 準備完了）。「設定を保存」を押してすぐ利用できます！",
    },
    "减少动效": {"en": "Reduce Motion", "ko": "모션 줄이기", "ja": "視差効果を減らす"},
    "刷新": {"en": "Refresh", "ko": "새로고침", "ja": "更新"},
    "冻结": {"en": "Freeze", "ko": "고정", "ja": "固定"},
    "恢复": {"en": "Resume", "ko": "재개", "ja": "再開"},
    "冻结画面": {"en": "Freeze View", "ko": "화면 고정", "ja": "画面固定"},
    "恢复画面": {"en": "Resume View", "ko": "화면 재개", "ja": "画面再開"},
    "⋯ 更多": {"en": "⋯ More", "ko": "⋯ 더보기", "ja": "⋯ その他"},
    "▴ 收起更多": {"en": "▴ Less", "ko": "▴ 접기", "ja": "▴ 閉じる"},
    "波形与 FFT 频谱": {"en": "Waveform && FFT", "ko": "파형 및 FFT 스펙트럼", "ja": "波形と FFT スペクトル"},
    "频带能量与声谱图": {"en": "Bands && Spectrogram", "ko": "대역 에너지 및 스펙트로그램", "ja": "帯域エネルギーとスペクトログラム"},
    "▾ 收起 A/B": {"en": "▾ Collapse A/B", "ko": "▾ A/B 접기", "ja": "▾ A/B を折りたたむ"},
    "▸ 展开 A/B": {"en": "▸ Expand A/B", "ko": "▸ A/B 펼치기", "ja": "▸ A/B を展開"},
    "时间 (秒)": {"en": "Time (s)", "ko": "시간 (초)", "ja": "時間 (秒)"},
    "最小化窗口": {"en": "Minimize Window", "ko": "창 최소화", "ja": "ウィンドウを最小化"},
    "选择音源…": {
        "en": "Select audio source…",
        "ko": "오디오 소스 선택…",
        "ja": "音源を選択…",
    },
    "开始捕获后显示": {
        "en": "Appears after capture starts",
        "ko": "캡처 시작 후 표시",
        "ja": "キャプチャ開始後に表示",
    },
    "选最近 30 s 并 2-Stem 分轨": {
        "en": "Select Last 30s && 2-Stem",
        "ko": "최근 30초 선택 후 2-Stem 분리",
        "ja": "直近30秒を選択して2-Stem分離",
    },
    "① 选中片段 → ② 选最近 30 s 并 2-Stem 分轨": {
        "en": "① Select Clip → ② Select Last 30s & 2-Stem",
        "ko": "① 구간 선택 → ② 최근 30초 선택 후 2-Stem 분리",
        "ja": "① 区間選択 → ② 直近30秒を選択して2-Stem分離",
    },
    "点击「选最近 30 s 并 2-Stem 分轨」，或在下方 120s 历史缓冲选定 A/B 区间后分轨；分离后的人声 / 伴奏 / 贝斯 / 鼓组独立波形轨、M/S 独听与单轨转 MIDI 按钮将在此处就位。": {
        "en": "Click 'Select Last 30s & 2-Stem' above, or select an A/B range in the 120s history buffer below; separated Vocals / Accompaniment / Bass / Drums waveforms, M/S soloing, and stem-to-MIDI buttons will appear here.",
        "ko": "위의 '최근 30초 선택 후 2-Stem 분리'를 클릭하거나 아래 120초 버퍼에서 A/B 구간을 선택하세요. 분리된 보컬/반주/베이스/드럼 파형과 M/S 솔로·MIDI 변환 버튼이 여기에 표시됩니다.",
        "ja": "上の「直近30秒を選択して2-Stem分離」をクリックするか、下の120秒履歴バッファでA/B区間を選択して分離してください。分離後の各トラック波形・M/S・MIDI変換ボタンがここに表示されます。",
    },
    "切换明暗主题": {"en": "Toggle Light/Dark Theme", "ko": "밝기/어두운 테마 전환", "ja": "ライト/ダーク切替"},
    "内存偏低": {"en": "Low RAM", "ko": "메모리 부족", "ja": "RAM不足"},
    "低内存": {"en": "Low RAM", "ko": "메모리 부족", "ja": "RAM少"},
    "[混入警告] 静音": {"en": "[Loopback Warn] Silent", "ko": "[루프백 경고] 무음", "ja": "[ループバック警告] 無音"},
    "[混入警告] 有信号": {"en": "[Loopback Warn] Signal", "ko": "[루프백 경고] 신호 있음", "ja": "[ループバック警告] 信号あり"},
    "已锁定": {"en": "Locked", "ko": "잠금", "ja": "ロック"},
    "已捕获": {"en": "Active", "ko": "활성", "ja": "稼働中"},
    "Normal": {"en": "Normal", "ko": "정상", "ja": "正常"},
    "Warning": {"en": "Warning", "ko": "경고", "ja": "警告"},
    "Critical": {"en": "Critical", "ko": "위험", "ja": "危険"},
    "Insufficient · 等待音频": {
        "en": "Insufficient · Waiting for audio",
        "ko": "데이터 부족 · 오디오 대기 중",
        "ja": "不足 · 音声待機中",
    },
    "Insufficient · 已重置，等待新音频": {
        "en": "Insufficient · Reset, waiting for new audio",
        "ko": "데이터 부족 · 초기화됨, 새 오디오 대기 중",
        "ja": "不足 · リセット済、新しい音声を待機中",
    },
    "显示与同步半速 BPM (÷2，不改分析器内部状态)": {
        "en": "Display & sync half-time BPM (÷2, without altering analyzer state)",
        "ko": "하프타임 BPM 표시 및 동기화 (÷2, 분석기 내부 상태 유지)",
        "ja": "ハーフタイム BPM 表示と同期 (÷2、解析器内部状態は変更なし)",
    },
    "显示与同步倍速 BPM (×2，不改分析器内部状态)": {
        "en": "Display & sync double-time BPM (×2, without altering analyzer state)",
        "ko": "더블타임 BPM 표시 및 동기화 (×2, 분석기 내부 상태 유지)",
        "ja": "ダブルタイム BPM 表示と同期 (×2、解析器内部状態は変更なし)",
    },
    "CHORD_PRACTICE · 练习和弦": {
        "en": "CHORD_PRACTICE · Practice Chords",
        "ko": "CHORD_PRACTICE · 코드 연습",
        "ja": "CHORD_PRACTICE · コード練習",
    },
    "RESET // TRACK · 换歌重置": {
        "en": "RESET // TRACK · Reset Harmony on Track Change",
        "ko": "RESET // TRACK · 곡 변경 시 화성 초기화",
        "ja": "RESET // TRACK · 曲切替で和声リセット",
    },
    "分轨后点击『分析和弦与节奏』": {
        "en": "Run stem separation, then click 'Analyze Chords & Rhythm'",
        "ko": "스템 분리 후 '코드 및 리듬 분석'을 클릭하세요",
        "ja": "分離後に「コードとリズムを解析」をクリック",
    },
    "最大化 / 还原窗口": {"en": "Maximize / Restore Window", "ko": "창 최대화 / 복원", "ja": "ウィンドウの最大化 / 復元"},
    "关闭 ListenScope": {"en": "Close ListenScope", "ko": "ListenScope 닫기", "ja": "ListenScope を閉じる"},
    "冻结/恢复实时频谱、和弦、调性与音准画面刷新 (快捷键 F)": {
        "en": "Freeze/Resume live spectrum, chord, key & pitch display (Shortcut: F)",
        "ko": "실시간 스펙트럼, 코드, 조성 및 음정 표시 일시정지/재개 (단축키 F)",
        "ja": "リアルタイムスペクトル・コード・調・音程表示の固定/再開 (ショートカット F)",
    },
    "LISTENSCOPE // 实时音频分析与吉他扒谱工作台": {
        "en": "LISTENSCOPE // Realtime Audio Analysis & Guitar Practice Workbench",
        "ko": "LISTENSCOPE // 실시간 오디오 분석 및 기타 연습 워크벤치",
        "ja": "LISTENSCOPE // リアルタイム音声解析＆ギター練習ワークベンチ",
    },
    "AUDIO_IN // 选择要捕获的音频进程或系统环回": {
        "en": "AUDIO_IN // Select audio process or system loopback to capture",
        "ko": "AUDIO_IN // 캡처할 오디오 프로세스 또는 시스템 루프백 선택",
        "ja": "AUDIO_IN // キャプチャするプロセスまたはシステムループバックを選択",
    },
    "CAPTURE_START // 开始或停止实时音频捕获 (Space)": {
        "en": "CAPTURE_START // Start or stop live audio capture (Space)",
        "ko": "CAPTURE_START // 실시간 오디오 캡처 시작/중지 (Space)",
        "ja": "CAPTURE_START // リアルタイム音声キャプチャ開始/停止 (Space)",
    },
    "CONFIG // 设置与系统状态": {
        "en": "CONFIG // Settings & System Status",
        "ko": "CONFIG // 설정 및 시스템 상태",
        "ja": "CONFIG // 設定・システム状態",
    },
    "E-STOP // 紧急停止所有 AI 任务并清理显存 (Ctrl+Shift+E)": {
        "en": "E-STOP // Emergency stop all AI jobs & free VRAM (Ctrl+Shift+E)",
        "ko": "E-STOP // 모든 AI 작업 긴급 정지 및 VRAM 정리 (Ctrl+Shift+E)",
        "ja": "E-STOP // 全 AI ジョブ緊急停止＆VRAM 解放 (Ctrl+Shift+E)",
    },
    "① 选中片段 → ② AI 2-Stem 分轨": {
        "en": "① Select Clip → ② AI 2-Stem Split",
        "ko": "① 구간 선택 → ② AI 2-Stem 분리",
        "ja": "① 区間選択 → ② AI 2-Stem 分離",
    },
    "打开单轨 WAV 转 MIDI…": {
        "en": "Open Stem WAV to MIDI…",
        "ko": "단일 스템 WAV → MIDI…",
        "ja": "単一ステム WAV → MIDI…",
    },
    "练习和弦": {"en": "Chord Practice", "ko": "코드 연습", "ja": "コード練習"},
    "换歌重置": {"en": "Reset Harmony", "ko": "화성 리셋", "ja": "和声リセット"},
    "刷新音频进程列表": {
        "en": "Refresh audio process list",
        "ko": "오디오 프로세스 목록 새로고침",
        "ja": "オーディオプロセス一覧を更新",
    },
    "展开或收起 A/B 微调、AI 分轨、导出、缩放与书签控件": {
        "en": "Expand or collapse A/B fine-tune, AI split, export, zoom & bookmark controls",
        "ko": "A/B 미세 조정, AI 분리, 내보내기, 확대/축소 및 북마크 컨트롤 펼치기/접기",
        "ja": "A/B 微調整・AI 分離・書き出し・ズーム・ブックマークの展開/折りたたみ",
    },
    "冻结界面遥测微动画（不影响实时频谱与和弦分析）": {
        "en": "Freeze UI telemetry micro-animations (does not affect live spectrum or chord analysis)",
        "ko": "UI 텔레메트리 미세 애니메이션 고정 (실시간 스펙트럼/코드 분석에 영향 없음)",
        "ja": "UI テレメトリの微細アニメーションを固定（リアルタイム解析には影響しません）",
    },
    "120秒历史缓冲与 A/B 片段 (~46MB)": {
        "en": "120s History Buffer & A/B Loop (~46MB)",
        "ko": "120초 히스토리 버퍼 · A/B 구간 (~46MB)",
        "ja": "120秒履歴バッファ・A/B 区間 (~46MB)",
    },
    "展开或收起 A/B 微调、导出、缩放与书签控件": {
        "en": "Expand or collapse A/B fine-tune, export, zoom & bookmark controls",
        "ko": "A/B 미세 조정, 내보내기, 확대/축소 및 북마크 컨트롤 펼치기/접기",
        "ja": "A/B 微調整・書き出し・ズーム・ブックマークの展開/折りたたみ",
    },
    "历史波形时间轴（秒）": {
        "en": "History Waveform Timeline (sec)",
        "ko": "히스토리 파형 타임라인 (초)",
        "ja": "履歴波形タイムライン（秒）",
    },
    "FFT 频谱倾斜补偿 (dB/oct)": {
        "en": "FFT Spectrum Slope Tilt (dB/oct)",
        "ko": "FFT 스펙트럼 기울기 보정 (dB/oct)",
        "ja": "FFT スペクトル傾斜補正 (dB/oct)",
    },
    "峰值 > -0.3 dBFS 削波锁存灯（点击清除）": {
        "en": "Peak > -0.3 dBFS Clip Latch Indicator (Click to clear)",
        "ko": "피크 > -0.3 dBFS 클리핑 래치 표시등 (클릭하여 해제)",
        "ja": "ピーク > -0.3 dBFS クリップラッチ表示（クリックで解除）",
    },
    "折叠或展开底部 120 秒历史缓冲与 A/B 分轨面板": {
        "en": "Collapse or expand the 120s history buffer & A/B stem panel",
        "ko": "하단 120초 히스토리 버퍼 및 A/B 분리 패널 접기/펼치기",
        "ja": "下部の 120 秒履歴バッファ・A/B 分離パネルを折りたたむ/展開",
    },
    "静态装饰锁定 (STATIC_DECOR) 与遥测微动画": {
        "en": "Static Decor Lock (STATIC_DECOR) & Telemetry Micro-Animations",
        "ko": "정적 장식 잠금 (STATIC_DECOR) 및 텔레메트리 미세 애니메이션",
        "ja": "静的装飾ロック (STATIC_DECOR) とテレメトリ微細アニメーション",
    },
    "• 右侧卡片上的跳动圆点、信号能量柱及电池分段条属于「遥测微动画」，开启音乐动态响应后会随音量与高潮实时变化。\n• 点击 [STATIC_DECOR] 可立即冻结底部装饰微动画（不影响主屏幕实时频谱/和弦刷新；如需冻结主屏幕请点顶栏「暂停/冻结画面」）。": {
        "en": "• The pulsing dots, band strips, and segmented battery bar are decorative telemetry micro-animations that react to audio energy when enabled.\n• Click [STATIC_DECOR] to freeze decorative animations without pausing live spectrum/chord updates (use the topbar Freeze View button to pause live plots).",
        "ko": "• 우측 카드의 맥동 점, 대역 스트립 및 배터리 분할 바는 오디오 에너지에 반응하는 장식용 텔레메트리 미세 애니메이션입니다.\n• [STATIC_DECOR]를 클릭하면 실시간 스펙트럼/코드 갱신에 영향을 주지 않고 장식 애니메이션만 즉시 고정할 수 있습니다.",
        "ja": "• 右側カードのパルス点・帯域ストリップ・バッテリーバーはオーディオに連動する装飾マイクロアニメーションです。\n• [STATIC_DECOR] を押すとリアルタイムスペクトル/コード更新を止めずに装飾アニメーションのみ固定できます。",
    },
    "⚠️ 当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。": {
        "en": "⚠️ System WASAPI Loopback active: audio from other apps may be mixed in.",
        "ko": "⚠️ 시스템 WASAPI 루프백 모드 사용 중: 다른 앱의 소리가 섞일 수 있습니다.",
        "ja": "⚠️ システム WASAPI ループバック使用中: 他アプリの音声が混入する可能性があります。",
    },
    "当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。": {
        "en": "System WASAPI Loopback active: audio from other apps may be mixed in.",
        "ko": "시스템 WASAPI 루프백 모드 사용 중: 다른 앱의 소리가 섞일 수 있습니다.",
        "ja": "システム WASAPI ループバック使用中: 他アプリの音声が混入する可能性があります。",
    },
    "曲目监测 (SMTC): 未检测到匹配会话，可继续使用右侧「换歌重置」": {
        "en": "Track Monitor (SMTC): No matching session detected; you can still use Reset Harmony on the right.",
        "ko": "트랙 모니터 (SMTC): 일치하는 세션이 감지되지 않았습니다. 오른쪽 '화성 리셋'을 계속 사용할 수 있습니다.",
        "ja": "トラック監視 (SMTC): 一致するセッションが検出されません（右側の「和声リセット」は使用可能）。",
    },
    "曲目监测 (SMTC): 元数据过渡中，保留当前历史": {
        "en": "Track Monitor (SMTC): Metadata transitioning; keeping current history.",
        "ko": "트랙 모니터 (SMTC): 메타데이터 전환 중, 현재 기록 유지.",
        "ja": "トラック監視 (SMTC): メタデータ移行中、現在の履歴を保持します。",
    },
    "曲目会话监测 (SMTC): 当前为合成测试信号源（可手动点「换歌重置」或注入 SMTC 模拟测试）": {
        "en": "SMTC Track Monitor: Synthetic test source active (click Reset Harmony or inject SMTC mock).",
        "ko": "트랙 세션 모니터 (SMTC): 합성 테스트 신호 소스 활성('화성 리셋' 또는 SMTC 모의 테스트 가능).",
        "ja": "曲目セッション監視 (SMTC): 合成テスト信号ソース稼働中（「和声リセット」または SMTC モック注入可）。",
    },
}

_PREFIX_REPLACEMENTS: tuple[tuple[str, dict[str, str]], ...] = (
    ("构成音:", {"en": "Tones:", "ko": "구성음:", "ja": "構成音:"}),
    ("相对级数:", {"en": "Roman Degree:", "ko": "상대 도수:", "ja": "相対度数:"}),
    ("第二候选:", {"en": "2nd Candidate:", "ko": "2순위 후보:", "ja": "第2候補:"}),
    ("稳定度:", {"en": "Stability:", "ko": "안정도:", "ja": "安定度:"}),
    ("节拍稳定度:", {"en": "Tempo Stability:", "ko": "템포 안정도:", "ja": "템ポ安定度:"}),
    ("主音高:", {"en": "Pitch:", "ko": "기본 음고:", "ja": "基本ピッチ:"}),
    ("低音 ", {"en": "Bass ", "ko": "베이스 ", "ja": "ベース "}),
    ("多声部 · 显示低音", {"en": "Polyphonic · Bass Pitch", "ko": "다성부 · 베이스 음고", "ja": "ポリフォニック · ベース音高"}),
    ("音量:", {"en": "Vol:", "ko": "볼륨:", "ja": "音量:"}),
    ("最近和弦进行 (最多 12 步):", {"en": "Recent Progression (<=12 steps):", "ko": "최근 코드 진행 (최대 12스텝):", "ja": "直近コード進行 (最大12ステップ):"}),
    ("曲目会话监测 (SMTC):", {"en": "SMTC Track Monitor:", "ko": "트랙 세션 모니터 (SMTC):", "ja": "曲目セッション監視 (SMTC):"}),
    ("曲目监测 (SMTC):", {"en": "Track Monitor (SMTC):", "ko": "트랙 모니터 (SMTC):", "ja": "トラック監視 (SMTC):"}),
    ("已缓冲:", {"en": "Buffered:", "ko": "버퍼링됨:", "ja": "バッファ済:"}),
    ("贝斯独听 +", {"en": "Bass Solo +", "ko": "베이스 솔로 +", "ja": "ベース独聴 +"}),
    ("循环范围:", {"en": "Loop Scope:", "ko": "루프 범위:", "ja": "ループ範囲:"}),
    ("当前和弦:", {"en": "Current Chord:", "ko": "현재 코드:", "ja": "現在コード:"}),
    ("[混入警告] 有信号 ·", {"en": "[Loopback Warn] Signal ·", "ko": "[루프백 경고] 신호 있음 ·", "ja": "[ループバック警告] 信号あり ·"}),
    ("[混入警告] 静音 ·", {"en": "[Loopback Warn] Silent ·", "ko": "[루프백 경고] 무음 ·", "ja": "[ループバック警告] 無音 ·"}),
    ("有信号 ·", {"en": "Signal ·", "ko": "신호 있음 ·", "ja": "信号あり ·"}),
    ("静音 ·", {"en": "Silent ·", "ko": "무음 ·", "ja": "無音 ·"}),
    ("注意：调性中心(Key)与调号(Key Signature)不同", {"en": "Note: Key center differs from Key Signature (relative/modal keys share signatures)", "ko": "참고: 조성 중심(Key)과 조표(Key Signature)는 다릅니다", "ja": "注: 調性中心(Key)と調号(Key Signature)は異なります"}),
)


UI_PHRASE_MAP.update(EXTRA_PHRASE_MAP)


def translate_help(title: str, explanation: str, lang: str) -> tuple[str, str]:
    """Translate a HelpBadge (title, explanation) pair into `lang`."""
    code = normalize_language(lang)
    if code == "zh":
        return title, explanation
    entry = HELP_TRANSLATIONS.get(title.strip())
    if entry and code in entry:
        return entry[code]
    # Fallback for dynamically generated help badges (e.g. CH-01 · 实时波形)
    t_out = translate_text(title, code)
    e_out = translate_text(explanation, code)
    return t_out, e_out


def translate_text(text: str, lang: str) -> str:
    """Translate an exact UI phrase, dynamic prefix phrase, or regex-matched runtime string."""
    code = normalize_language(lang)
    if code == "zh" or not text:
        return text
    stripped = text.strip()
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]

    entry = UI_PHRASE_MAP.get(stripped)
    if entry and code in entry:
        return f"{lead}{entry[code]}{trail}"
    # Also check unstripped (important for SpinBox prefixes like "倒退 ")
    entry_raw = UI_PHRASE_MAP.get(text)
    if entry_raw and code in entry_raw:
        return entry_raw[code]

    out = text
    for zh_prefix, trans_map in _PREFIX_REPLACEMENTS:
        if stripped.startswith(zh_prefix) and code in trans_map:
            if zh_prefix.startswith("注意：调性中心"):
                return trans_map[code]
            out = f"{lead}{trans_map[code]}{stripped[len(zh_prefix):]}{trail}"
            break

    for pat, repl_map in DYNAMIC_REGEX_RULES:
        if code in repl_map and pat.search(out):
            out = pat.sub(repl_map[code], out)

    # Final safety pass for "EN_TAG // 中文" strings when switching to English: strip Chinese suffix cleanly
    if code == "en" and " // " in out and _ZH_CHAR_RE.search(out):
        left, right = out.split(" // ", 1)
        if not _ZH_CHAR_RE.search(left) and _ZH_CHAR_RE.search(right):
            mapped_right = UI_PHRASE_MAP.get(right.strip(), {}).get("en")
            if mapped_right and mapped_right.lower() != left.strip().lower():
                out = f"{left} // {mapped_right}"
            else:
                out = left
    return out


def _translate_cached(
    obj: QtWidgets.QWidget,
    cur: str,
    prop_key: str,
    code: str,
    *,
    apply_fn,
) -> None:
    orig = obj.property(prop_key)
    if orig is None:
        if not cur:
            return
        # Cache if it's translatable or contains Chinese characters
        probe = translate_text(cur, "en")
        if probe != cur or _ZH_CHAR_RE.search(cur):
            obj.setProperty(prop_key, cur)
            orig = cur
        else:
            return
    orig_str = str(orig)
    target = orig_str if code == "zh" else translate_text(orig_str, code)
    if target is not None and cur != target:
        apply_fn(target)


def set_i18n_text(widget: QtCore.QObject, zh_text: str) -> None:
    """Update a dynamic widget's text while refreshing _ls_orig_text for language switches."""
    orig = str(zh_text)
    widget.setProperty("_ls_orig_text", orig)
    code = get_current_language()
    target = orig if code == "zh" else translate_text(orig, code)
    setter = getattr(widget, "setText", None)
    if callable(setter):
        setter(target)


def translate_widget_tree(root: QtWidgets.QWidget, lang: str) -> None:
    """Recursively translate labels, buttons, groupboxes, tabs, combos, tables, spinboxes, plots, and HelpBadges.

    Caches the original Chinese text in widget properties (`_ls_orig_*`) so switching
    `zh` <-> `en` <-> `ko` <-> `ja` is 100% lossless and idempotent.
    """
    code = set_current_language(lang)
    try:
        import pyqtgraph as pg  # type: ignore[import-untyped]
    except Exception:
        pg = None  # type: ignore[assignment]
    try:
        from ui.help_badge import HelpBadge
    except Exception:
        HelpBadge = None  # type: ignore[assignment,misc]

    # Window title on root dialog/window
    if isinstance(root, (QtWidgets.QDialog, QtWidgets.QMainWindow)):
        _translate_cached(root, root.windowTitle(), "_ls_orig_wintitle", code, apply_fn=root.setWindowTitle)

    for act in root.findChildren(QtGui.QAction):
        if act.text():
            _translate_cached(act, act.text(), "_ls_orig_text", code, apply_fn=act.setText)
        if act.toolTip():
            _translate_cached(act, act.toolTip(), "_ls_orig_tip", code, apply_fn=act.setToolTip)

    widgets = [root, *root.findChildren(QtWidgets.QWidget)]
    for w in widgets:
        if HelpBadge is not None and isinstance(w, HelpBadge):
            w.apply_language(code)
            continue
        if w.accessibleName():
            _translate_cached(w, w.accessibleName(), "_ls_orig_an", code, apply_fn=w.setAccessibleName)
        if w.toolTip() and not w.property("_ls_dynamic_tip"):
            _translate_cached(w, w.toolTip(), "_ls_orig_tip", code, apply_fn=w.setToolTip)
        if isinstance(w, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
            _translate_cached(w, w.text(), "_ls_orig_text", code, apply_fn=w.setText)
        elif isinstance(w, QtWidgets.QGroupBox):
            _translate_cached(w, w.title(), "_ls_orig_title", code, apply_fn=w.setTitle)
        elif isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QPlainTextEdit)):
            _translate_cached(
                w,
                w.placeholderText(),
                "_ls_orig_placeholder",
                code,
                apply_fn=w.setPlaceholderText,
            )
        elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            _translate_cached(w, w.prefix(), "_ls_orig_prefix", code, apply_fn=w.setPrefix)
            _translate_cached(w, w.suffix(), "_ls_orig_suffix", code, apply_fn=w.setSuffix)
        elif isinstance(w, QtWidgets.QTabWidget):
            for idx in range(w.count()):
                _translate_cached(
                    w,
                    w.tabText(idx),
                    f"_ls_orig_tab_{idx}",
                    code,
                    apply_fn=lambda t, _w=w, _i=idx: _w.setTabText(_i, t),
                )
        elif isinstance(w, QtWidgets.QComboBox) and not isinstance(w, QtWidgets.QFontComboBox):
            if bool(w.property("lsKeepItems")):
                continue
            for idx in range(w.count()):
                _translate_cached(
                    w,
                    w.itemText(idx),
                    f"_ls_orig_item_{idx}",
                    code,
                    apply_fn=lambda t, _w=w, _i=idx: _w.setItemText(_i, t),
                )
        elif isinstance(w, QtWidgets.QTableWidget):
            for col in range(w.columnCount()):
                hdr = w.horizontalHeaderItem(col)
                if hdr is not None:
                    _translate_cached(
                        w,
                        hdr.text(),
                        f"_ls_orig_hdr_{col}",
                        code,
                        apply_fn=lambda t, _h=hdr: _h.setText(t),
                    )
            for row in range(w.rowCount()):
                for col in range(w.columnCount()):
                    item = w.item(row, col)
                    if item is not None:
                        _translate_cached(
                            w,
                            item.text(),
                            f"_ls_orig_cell_{row}_{col}",
                            code,
                            apply_fn=lambda t, _it=item: _it.setText(t),
                        )
        elif pg is not None and isinstance(w, pg.PlotWidget):
            plot_item = w.getPlotItem()
            title_lbl = getattr(plot_item, "titleLabel", None)
            if title_lbl is not None and getattr(title_lbl, "text", ""):
                cur_title = str(title_lbl.text)
                _translate_cached(
                    w,
                    cur_title,
                    "_ls_orig_plottitle",
                    code,
                    apply_fn=lambda t, _pi=plot_item: _pi.setTitle(t),
                )
            for ax_name in ("bottom", "left", "top", "right"):
                ax = plot_item.getAxis(ax_name)
                if ax is not None and getattr(ax, "labelText", ""):
                    cur_ax = str(ax.labelText)
                    _translate_cached(
                        w,
                        cur_ax,
                        f"_ls_orig_axis_{ax_name}",
                        code,
                        apply_fn=lambda t, _pi=plot_item, _an=ax_name: _pi.setLabel(
                            _an,
                            t,
                            **(
                                {
                                    "font-size": "9pt",
                                    "color": _pi.getAxis(_an).labelStyle["color"],
                                }
                                if _pi.getAxis(_an).labelStyle.get("color")
                                else {"font-size": "9pt"}
                            ),
                        ),
                    )

