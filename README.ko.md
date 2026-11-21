# ListenScope

[简体中文](README.md) | [English](README.en.md) | 한국어 | [日本語](README.ja.md)

**무료 · 오프라인 · 로컬 실행** Windows 데스크톱 음악 분석, A/B 루프, AI 스템 분리 및 카피/채보 연습 워크스테이션입니다.

암호화된 음원 캐시를 내려받거나 가상 오디오 드라이버를 설정할 필요가 없습니다. 음악 플레이어나 브라우저에서 재생 중인 소리를 표준 Windows WASAPI로 프로세스 단위 캡처해 실시간 스펙트럼, 코드 진행, 조성(Key), BPM, 120초 구간 반복, 로컬 AI 스템 분리 및 Cubase 호환 MIDI 내보내기를 제공합니다.

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope 데모" width="880" />
</p>

---

## 빠른 시작 (명령어 불필요 · 그래픽 UI 원클릭 설정)

대부분의 사용자는 터미널을 열 필요 없이 4단계만으로 바로 사용할 수 있습니다:

1. **다운로드 및 설치**: [Releases](https://github.com/Ceph-learner/ListenScope/releases)에서 `ListenScope-Setup-Windows-x64.exe` 또는 `ListenScope-Core-Windows-x64-Portable.zip`을 다운로드합니다.
2. **실행**: `ListenScope.exe`를 더블 클릭합니다. **실시간 스펙트럼, 코드/조성/BPM 분석, 120초 A/B 변속 루프, 메트로놈은 별도 설치 없이 즉시 작동**합니다.
3. **GUI에서 AI & MIDI 원클릭 설정 (선택 사항)**:
   - 우측 상단 **`CONFIG // 설정`** → **`AI & MIDI 환경`** 으로 이동합니다(아래 이미지 참고).
   - 이미 PyTorch / Conda가 설치되어 있다면 **로컬 PyTorch 스캔**을 클릭하고,
   - 설치되어 있지 않다면 **AI + MIDI 원클릭 자동 구성**을 누르면 의존성을 자동 설치한 뒤 **재시작** 버튼으로 즉시 적용됩니다.
4. **분석 시작**: 상단 `AUDIO_IN`에서 재생 중인 플레이어나 브라우저를 선택하고 **`CAPTURE_START`**를 클릭하세요.

<p align="center">
  <img src="docs/images/settings_ai.png" alt="GUI AI & MIDI 원클릭 설정" width="760" />
</p>

---

## 화면 및 기능 미리보기

| 실시간 스펙트럼 (클리니컬 라이트 · 기본) | 다크 모드 (`VOID // 다크` 빠른 전환) |
| :---: | :---: |
| <img src="docs/images/main_light.png" alt="라이트 모드" width="440" /> | <img src="docs/images/main_dark.png" alt="다크 모드" width="440" /> |

| 코드 · 조성 · 튜닝 바 및 연습 창 | 핵심 기능 |
| :---: | :--- |
| <img src="docs/images/chroma.png" alt="Chroma 및 코드 분석" width="440" /> | • **실시간 캡처 및 스펙트럼**: Windows 프로세스 루프백(Build ≥ 20348), 실시간 파형, FFT/로그 스펙트럼, `F0` 피치 및 `-50 ~ +50 cents` 튜닝 바.<br>• **코드 · 조성 · 카포**: 12-bin Chroma 히트맵, 로마 숫자 도수, CPU **카포/이조**, 24조 코드 연습 창(미리듣기 및 `.mid` 내보내기).<br>• **120초 A/B 루프**: 고정 120초 링 버퍼, `0.5x–1.25x` 음정 유지 WSOLA 속도 조절, 12개 북마크, Tap 메트로놈 및 연습 WAV 내보내기.<br>• **로컬 AI 스템 및 MIDI**: 2-Stem / 4-Stem 분리, **`0–24 dB` 베이스 솔로 부스트**, `B0`/`E1`까지 측정하는 FFT-YIN 및 **Cubase 호환 SMF Type-0 (`480 TPB`) MIDI**. |

---

<details>
<summary><b>개발자용: 소스에서 실행 및 테스트</b></summary>

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

## 문서 및 라이선스

- [아키텍처 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) · [설계 결정 (docs/DECISIONS.md)](docs/DECISIONS.md) · [개발 가이드 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md) · [패키징 (docs/PACKAGING.md)](docs/PACKAGING.md) · [기여 안내 (CONTRIBUTING.md)](CONTRIBUTING.md)
- [MIT License](LICENSE) · [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
