# ListenScope

<p align="left">
  <a href="README.md">简体中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/Platform-Windows%2011%20%7C%20Win10%20(System%20Loopback)-0078D4?style=flat-square" alt="Windows" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
  <a href="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml"><img src="https://github.com/Ceph-learner/ListenScope/actions/workflows/tests.yml/badge.svg" alt="Tests" /></a>
</p>

무료 · 오프라인 · 로컬 실행 방식의 Windows 데스크톱 음악 분석, A/B 루프 연습 및 채보 보조 워크스테이션입니다. 작성자와 AI 어시스턴트의 협업으로 개발되었으며, 가볍고 제어 가능한 로컬 오디오 분석 환경을 지향합니다.

---

## 1. 스크린샷

![실시간 스펙트럼 및 파형 분석 (라이트 테마)](docs/images/listenscope_light_spectrum_1366x768.png)

| 다크 테마 (영문) | 코드 · 조성 · 템포 | 스템 믹서 · MIDI |
| :---: | :---: | :---: |
| ![다크 테마](docs/images/listenscope_dark_en_spectrum_1366x768.png) | ![코드 및 조성](docs/images/listenscope_light_chord_1366x768.png) | ![스템 믹서](docs/images/listenscope_light_mixer_empty_1366x768.png) |

> 위 스크린샷은 모두 `scripts/make_screenshots.py`로 합성 오디오에서 오프스크린 생성되었으며 실제 곡 제목이나 개인 경로를 포함하지 않습니다.

---

## 2. 주요 기능 (검증됨)

- **실시간 캡처 및 스펙트럼**: 표준 Windows WASAPI 프로세스 루프백(Windows 11 Build ≥ 20348) 또는 시스템 루프백(Windows 10/11)으로 재생 중인 소리를 캡처하여 파형, FFT/로그 스펙트럼, `F0` 피치 및 `-50 ~ +50 cents` 튜닝 바를 제공합니다.
- **코드 · 조성 · 이조**: 12-bin Chroma 히트맵, 장/단 3화음 인식, 로마 숫자 도수, 12단계 코드 트레일, CPU 카포 이조, 24조 코드 연습 창(미리듣기 및 `.mid` 내보내기)을 지원합니다.
- **120초 기록 및 A/B 루프**: 고정 120초 링 버퍼(`48 kHz / Stereo / float32`), 드래그 A/B 구간 선택, `0.5x–1.25x` 음정 유지 WSOLA 속도 조절, 12개 북마크, Tap 메트로놈 및 연습 WAV 내보내기를 제공합니다.
- **로컬 AI 스템 분리 및 믹서(선택 사항)**: 독립 서브프로세스에서 2-Stem(MDX-Net) 또는 4-Stem(HTDemucs) 분리를 실행하며, 6초 안전 청크 및 즉시 정지(E-STOP) 메모리 해제, `0–24 dB` 베이스 솔로 부스트, FFT-YIN 베이스 피치 분석을 지원합니다.
- **MIDI 내보내기 및 Cubase 호환**: 스템 또는 단일 WAV 파일을 원클릭으로 Steinberg Cubase 호환 SMF Type-0(`480 TPB`) MIDI로 변환합니다.
- **테마 및 4개국어 지원**: 라이트/다크 전환, 여러 내장 테마 및 중국어(간체) / 영어 / 한국어 / 일본어 실시간 전환을 지원합니다.

---

## 3. 시스템 요구 사항

- **운영체제**: Windows 11 / Windows 10 (64비트). **프로세스 루프백은 Windows 11(Build ≥ 20348)이 필요하며, Windows 10에서는 시스템 루프백을 사용할 수 있습니다.**
- **검증 기준 하드웨어**: 실기 검증은 주로 **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM** 환경에서 수행되었습니다. 기타 GPU 및 구성은 아직 충분히 검증되지 않았습니다.
- **GPU 요구 사항**: **AI 스템 분리는 선택 기능**입니다. 실시간 스펙트럼, 코드/조성/BPM 분석, A/B 루프, 메트로놈은 CPU만으로 동작합니다.

---

## 4. 다운로드 및 설치

[Releases](https://github.com/Ceph-learner/ListenScope/releases)에서 다운로드할 수 있습니다:

- **설치 버전**: `ListenScope-Setup-Windows-x64.exe` (제거 시 `exports\` 폴더 보존).
- **포터블 버전**: `ListenScope-Core-Windows-x64-Portable.zip` (압축 해제 후 바로 실행; `settings.json` 및 내보내기 파일은 실행 폴더에 저장).

**무결성 검증 및 SmartScreen 안내**:
- 상용 코드 서명 인증서가 적용되어 있지 않아 첫 실행 시 Windows SmartScreen 경고가 표시될 수 있습니다(「추가 정보 → 실행」).
- 다운로드 후 릴리스의 `SHA256SUMS.txt`로 해시를 확인하세요(PowerShell: `Get-FileHash <파일명> -Algorithm SHA256`).
- 공식 Core 릴리스에는 **FFmpeg가 포함되어 있지 않습니다**. 필요한 경우 사용자가 별도로 설치하거나 배치하여 사용할 수 있습니다.

---

## 5. 빠른 시작

1. `ListenScope.exe`를 실행합니다(GPU 없이도 모든 실시간 분석 및 A/B 연습 기능을 사용할 수 있습니다).
2. *(선택 사항)* AI 분리나 WAV→MIDI를 사용하려면 설정 → **`AI & MIDI 환경`** 에서 로컬 PyTorch 스캔 또는 독립 런타임 구성을 진행하세요.
3. 상단 바에서 재생 중인 오디오 프로세스를 선택하고 캡처를 시작합니다.

자세한 사용법과 활용 시나리오는 [사용자 가이드 (docs/USER_GUIDE.en.md)](docs/USER_GUIDE.en.md) 또는 [중문 가이드](docs/USER_GUIDE.md)를 참고하세요.

---

## 6. 업데이트 안내

- 현재는 GitHub Releases 페이지에서 최신 설치 파일이나 포터블 압축 파일을 수동으로 내려받아 덮어쓰기 업데이트를 진행해야 합니다(포터블 버전은 `settings.json`, `exports/`, 로컬 환경 폴더를 유지하세요).
- 앱 내 온라인 업데이트 확인 기능은 추후 릴리스에 추가될 예정입니다(공개 릴리스 메타데이터만 읽으며 사용자 데이터를 업로드하지 않습니다).

---

## 7. 자주 묻는 질문 (FAQ)

- **NVIDIA GPU가 없어도 사용할 수 있나요?** 네. AI 분리는 선택 기능이며 나머지 모든 분석/연습 기능은 CPU만으로 작동합니다.
- **캡처 시 소리가 들어오지 않으면?** 올바른 재생 프로세스를 선택했는지 확인하거나 시스템 루프백으로 테스트해 보세요.
- **완전히 종료하려면?** 트레이 최소화가 켜져 있다면 시스템 트레이 아이콘을 마우스 오른쪽 버튼으로 클릭해 종료하세요.

자세한 내용은 [FAQ (docs/FAQ.en.md)](docs/FAQ.en.md) 및 [용어집 (docs/GLOSSARY.en.md)](docs/GLOSSARY.en.md)을 참고하세요.

---

## 8. 알려진 제한 사항

- 프레임리스 창은 아직 Windows 11 Snap Layouts(최대화 버튼 호버 메뉴)을 지원하지 않습니다.
- 기준 환경(Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM) 외의 하드웨어 구성은 충분히 테스트되지 않았습니다.

---

## 9. 기여하기

Issue 및 Pull Request를 환영합니다. Core 환경은 PyTorch / CUDA / TensorFlow 없이 동작하도록 3환경 격리 구조를 유지합니다:

```bash
# Linux / 오프스크린 테스트
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

자세한 내용은 [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/TESTING.md](docs/TESTING.md), [ROADMAP.md](ROADMAP.md)를 참고하세요.

---

## 10. 라이선스 · 개인정보 · 면책 조항

- **라이선스**: [MIT License](LICENSE) (`Copyright (c) 2026 Ceph-learner and ListenScope contributors`). 서드파티 고지 및 라이선스 원문은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)와 [licenses/](licenses/)에, 알고리즘 출처 감사는 [docs/PROVENANCE.md](docs/PROVENANCE.md)에 있습니다.
- **모델 가중치**: 본 저장소와 공식 릴리스에는 AI 모델 가중치 파일이 **포함되어 있지 않습니다**. 각 모델(UVR / MDX-Net, HTDemucs, Basic Pitch)은 실행 시 업스트림에서 다운로드되며 각자의 라이선스 및 이용 약관을 따릅니다.
- **면책 조항**:
  - 본 프로젝트는 Tencent, QQ Music 및 기타 음악 플랫폼과 어떠한 제휴 관계도 없습니다.
  - 표준 OS 오디오 API를 통해 재생 중인 소리만 캡처하며 DRM 우회, 복호화, 다운로드를 수행하지 않습니다.
  - 처리하는 오디오의 저작권 및 관련 법규 준수 책임은 사용자에게 있습니다.
  - 본 소프트웨어는 어떠한 보증도 없이 "있는 그대로" 제공됩니다. 상업적 용도로 사용할 경우 별도로 법적/라이선스 검토를 진행하시기 바랍니다.
- **상표**: QQ Music, Cubase, NVIDIA / RTX, Windows 등의 명칭은 각 권리자의 상표이며 본 프로젝트와 무관합니다.
- **개인정보 및 AI 협업 파일**: 모든 기능은 로컬에서 실행되며 원격 측정이 없습니다([PRIVACY.md](PRIVACY.md)). `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/HANDOFF.md`, `docs/AI_COLLABORATION.md`, `docs/review/`는 프로젝트 제약과 협업 맥락 기록용으로 유지됩니다.

---

## 11. 감사의 말

오디오 신호 처리, 음원 분리, MIDI 변환 및 데스크톱 UI 생태계에 기여해 주신 모든 오픈소스 프로젝트와 연구자분들께 감사드립니다. 전체 출처와 링크는 [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)에 보존되어 있습니다.
