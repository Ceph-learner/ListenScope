# Release v1.1.0 Preparation Audit Report (Issue #37)

- **Branch**: `release/v1.1-prep` (cut from `main` @ `f4fcaf1`)
- **Auditor**: Neon（只出审计报告与清单，不改业务代码、不删分支、不改仓库设置、不推 tag）
- **Audit Scope**: `R5-1`（全历史/全分支密钥扫描）、`R5-2`（个人信息与提交邮箱扫描）、`R5-3`（全量远程分支清单）、`R1-9`（算法与数据来源审计草稿 [`docs/PROVENANCE.md`](../PROVENANCE.md)）

---

## 一、Issue #37 审计条目状态表

| ID | 状态 | 验收方式 | 结果 |
|---|---|---|---|
| **R1-1** | `DONE` | 核对 `LICENSE` 版权行及四语言 README 一致性 | 已更新 `LICENSE` 为 `Copyright (c) 2026 Ceph-learner and ListenScope contributors`，四语言 README 许可证段一致。 |
| **R1-2** | `DONE (NEEDS_TARGET)` | Linux Core `pip-licenses` + `importlib.metadata` 依赖树生成 `THIRD_PARTY_NOTICES.md`，Windows 专属包按 PyPI 元数据补录 | 已生成 [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)（含 Qt/PySide6 LGPL-3.0、`soxr` LGPL-2.1-or-later、`certifi` MPL-2.0 提示及可替换说明）；`proc-tap`/`pycaw`/`comtypes`/`PyAudioWPatch`/`winrt-*` 标注 `待 Windows 构建核对`。 |
| **R1-3** | `DONE (NEEDS_TARGET)` | 检查 `packaging/listenscope_core.spec` 与 `.github/workflows/release-windows.yml` | 已将 `LICENSE`、`THIRD_PARTY_NOTICES.md`、`ACKNOWLEDGMENTS.md`、`licenses/` 加入 spec 与 Windows release 打包前置步骤（实际 ZIP/EXE 产物待 Windows CI 核验）。 |
| **R1-4** | `DONE` | 核对 `release-windows.yml` 与四语言 README | 确认 Core 发行包不内置 FFmpeg；已在四语言 README 与 `THIRD_PARTY_NOTICES.md` 注明「FFmpeg 由用户自行安装或选用」。 |
| **R1-5** | `DONE` | 核对 `ACKNOWLEDGMENTS.md` 与四语言 README | 已写明仓库与发行包不含模型权重，各模型遵循各自许可证与条款，需用户自行核对。 |
| **R1-6** | `DONE` | `rg` 扫描 `qfluentwidgets`/`FluentWindow`/`SettingCardGroup` + 核对 `ui/assets/settings/LICENSE.txt` | 0 处复制 GPL 代码；Lucide 许可证保留于 `ui/assets/settings/LICENSE.txt` 与 `licenses/ISC-Lucide.txt`。 |
| **R1-7** | `DONE` | 检查四语言 README 免责声明 | 四语言 README 均已补齐无关联、仅捕获本机播放输出不绕过 DRM、版权自负及按原样提供免责声明。 |
| **R1-8** | `DONE` | 比对 `ACKNOWLEDGMENTS.md` 修改前后内容 | 完整保留原有致谢内容，补充 Temperley (1999)/Shaath/Albrecht 引用及模型权重条款说明。 |
| **R1-9** | `DONE` | `analysis/key_detection.py` 更名 + A-BENCH / `realistic_mix` / `test_key_detection_accuracy.py` 前后对比 + 定稿 `docs/PROVENANCE.md` | `"keyfinder"` 已更名为 `"temperley1999"`（保留别名）；`algo_benchmark.py` 与 `realistic_mix.py` 前后 `diff -u` 完全一致，`test_key_detection_accuracy.py` 5 passed；`docs/PROVENANCE.md` 已定稿。 |
| **R1-10** | `DONE` | 检查四语言 README 商标声明 | 四语言 README 均已补齐 QQ 音乐、Cubase、NVIDIA/RTX、Windows 商标归属与无关联声明。 |
| **R3-1** | `DONE` | 检查 `README.md`、`README.en.md`、`README.ja.md`、`README.ko.md` | 四语言 README 已按 12 段结构重排，语气谦虚，仅列已实测功能，截图位置留 `TODO` 占位（待 #42 合并）。 |
| **R3-2** | `DONE` | `rg` 检查 `docs/` 硬编码旧版本号 | 已移除 `docs/ARCHITECTURE.md`（`0.2.1`）与 `docs/DEVELOPMENT.md`（`0.2.4`）硬编码，统一引用 `pyproject.toml`。 |
| **R3-4** | `DONE` | 检查社区治理与模板文件 | 已更新 `CONTRIBUTING.md`，新增 `CODE_OF_CONDUCT.md`、`SECURITY.md`、`CHANGELOG.md`、YAML Issue 表单与 `PULL_REQUEST_TEMPLATE.md`。 |
| **R3-5** | `DONE` | `rg` 扫描内部文档个人路径与凭据 + README 说明 | 无真实个人路径或凭据；已在四语言 README 说明 `AGENTS.md`/`docs/review/` 等协作文件用途。 |
| **R3-6** | `DONE` | 检查用户文档与双语覆盖 | 已新增中英双语 [`docs/USER_GUIDE.md`](../USER_GUIDE.md)/[`.en.md`](../USER_GUIDE.en.md)、[`docs/FAQ.md`](../FAQ.md)/[`.en.md`](../FAQ.en.md)、[`docs/GLOSSARY.md`](../GLOSSARY.md)/[`.en.md`](../GLOSSARY.en.md)。 |
| **R3-7** | `DONE` | 检查开发者文档与配置 | 已更新 `docs/DEVELOPMENT.md` 与 `CONTRIBUTING.md`（含 AI 辅助开发说明），新增 [`docs/TESTING.md`](../TESTING.md)、[`docs/I18N.md`](../I18N.md)、[`ROADMAP.md`](../../ROADMAP.md)、[`.editorconfig`](../../.editorconfig)。 |
| **R3-8** | `DONE (ACTION FOR OWNER)` | 检查 `.github/` 配置文件与操作指南 | 已新增 YAML Issue 表单、`PULL_REQUEST_TEMPLATE.md`、`CODEOWNERS`、`dependabot.yml`、`PRIVACY.md`、`SUPPORT.md`；仓库网页设置已写入 [`REPO_SETTINGS_GUIDE.md`](REPO_SETTINGS_GUIDE.md) 待主人操作，未改动任何仓库设置。 |
| **R5-1** | `AUDITED (CLEAN)` | 遍历 `git rev-list --objects --all` 共 1,737 个唯一对象（覆盖全 39 个远程分支与全部 tag），匹配 PAT / AWS / Google / OpenAI / Slack / Private Key 及 `.env`/`.pem`/`.key` | **0 个密钥命中**，**0 个敏感文件名**。 |
| **R5-2** | `AUDITED (ACTION FOR OWNER)` | 全历史 `git log --all` 作者邮箱汇总 + `HEAD`/`archive/internal-docs`/全历史 1,737 对象路径与邮箱扫描 | `HEAD` 与全历史文件 **0 处真实个人 Windows 路径**（仅有 `tests/test_review_phase1.py` 的合成占位 `C:\Users\Alice` 及 `archive/internal-docs` 中云端沙盒 `/home/antigravity`）；但 **Git 提交历史中有 39 次提交包含主人个人 Gmail 邮箱**（含 GitHub merge commit），需主人按 R1-11 操作启用 GitHub noreply 隐私设置并决定是否接受历史记录。 |
| **R5-3** | `AUDITED (AWAITING OWNER)` | 统计 `origin` 全部 39 个远程分支与 `origin/main` 合并关系 | 共 39 个远程分支：**建议删除 25 个已合并分支**、**必须保留 4 个**（`main` + 3 个 `backup/*`）、**待主人审查决定 10 个**（1 个 `archive/internal-docs` + 1 个活跃 `feature/ui-polish-p2e` + 8 个历史未合并 `design/*`/`feature/*`/`fix/*`）。 |

---

## 二、R5-1｜全历史与全分支密钥扫描详情

- **扫描范围**：`git fetch origin '+refs/heads/*:refs/remotes/origin/*'` 拉取全部 39 个远程分支与全部 tag，扫描 `git rev-list --objects --all` 去重后的 **1,737 个文本对象**。
- **检测规则**：GitHub Token（`ghp_` / `github_pat_` / `gho_` / `ghu_` / `ghs_` / `ghr_`）、AWS Access Key（`AKIA...`）、Google API Key（`AIza...`）、OpenAI Key（`sk-...`）、Slack Token（`xox[baprs]-...`）、PEM/OpenSSH 私钥头（`-----BEGIN ... PRIVATE KEY-----`），以及 `.env` / `.env.*` / `.pem` / `.key` / `.p12` / `.pfx` 文件名。
- **扫描结果**：**0 处密钥命中，0 个敏感文件**。
- **建议（R5-4）**：公开仓库前在 GitHub 网页开启 **Secret scanning** 与 **Push protection** 作为持续防线（本机亦可补跑一次 `gitleaks detect --source . --log-opts="--all"` 二次复核）。

---

## 三、R5-2 & R1-11｜个人信息与提交邮箱扫描详情

1. **当前 `HEAD`（`f4fcaf1`）跟踪文件**：
   - `C:\Users\` / `/home/` / `/Users/`：**0 处真实个人路径**（仅 `tests/test_review_phase1.py:174,177` 中测试占位符 `C:\Users\Alice`）。
   - 非 noreply 个人邮箱：**0 处命中**。
2. **全历史 1,737 个对象（含全部 `backup/*` 与 `archive/internal-docs`）**：
   - 真实 Windows 用户名路径（`C:\Users\<real>`）：**0 处命中**。
   - `origin/archive/internal-docs` 的归档 `docs/HANDOFF.md:89,134` 含 2 处云端沙盒路径 `/home/antigravity/.venv_test/bin/python`（非主人本机路径）。
3. **Git 提交作者邮箱（`git log --all`）**：
   - `Antigravity <noreply@github.com>`：69 次
   - `Ceph-learner <353659952+Ceph-learner@users.noreply.github.com>`：65 次
   - `Codex <codex@users.noreply.github.com>`：49 次
   - `Ceph-learner <p***@gmail.com>`（主人主 Gmail 邮箱）：**39 次**（包含通过 GitHub 网页 / `gh pr merge` 产生的 merge commit）
4. **给主人的隐私保护操作说明（R1-11）**：
   - 打开 GitHub → **Settings → Emails**，勾选 **Keep my email addresses private** 与 **Block command line pushes that expose my email**；
   - 本机执行 `git config --global user.email "353659952+Ceph-learner@users.noreply.github.com"`；
   - 历史中的 39 次提交在不改写历史（不 `force push`）的前提下无法抹去，公开前请主人确认是否接受。

---

## 四、R5-3｜全量 39 个远程分支清理清单（待主人确认后执行）

> **统计汇总**：总计 **39** 个远程分支（另加本审计分支 `release/v1.1-prep`）：
> - **建议删除（已合并至 `main`）**：**25** 个
> - **必须保留（`main` + `backup/*`）**：**4** 个
> - **需主人审查/活跃保留**：**10** 个（`archive/internal-docs` 1 个 + 当前活跃 `feature/ui-polish-p2e` 1 个 + 历史未合并 `design/*`/`feature/*`/`fix/*` 8 个）

| 分类 | 数量 | 处置建议 | 分支列表 |
|---|---|---|---|
| **主分支** | 1 | **保留** | `main` |
| **规则保护备份（`backup/*`）** | 3 | **必须保留**（`AGENTS.md` 禁止删除） | `backup/phase0-10-audit`、`backup/phase0-13-audit3`、`backup/phase0-phase1` |
| **内部文档归档（`archive/*`）** | 1 | **主人审查决定**（保留 / 迁至私有库 / 删除） | `archive/internal-docs`（含历史交接草稿与云端路径 `/home/antigravity`） |
| **当前活跃开发分支** | 1 | **暂保留**（待 #42 合并后删除） | `feature/ui-polish-p2e`（`+2`） |
| **已合并至 `main` 的历史分支** | **25** | **建议删除** | `docs/ai-memory-audit`、`feat/key-detection-upgrade`、`feature/appearance-presets`、`feature/live-playback-diagnostics`、`feature/settings-categories`、`fix/ab-playback-diagnostics`、`fix/continuous-import-resampling`、`fix/cuda-wheel-preflight`、`fix/live-loopback-feedback`、`fix/live-output-overwrite-diagnostics`、`fix/live-output-ring`、`fix/live-practice-reliability`、`fix/live-rtf-hop-timing`、`fix/offline-stem-seams`、`fix/review-p2a-engine`、`fix/review-p2b-algo`、`fix/review-p2c-ui`、`fix/review-p2d-windows`、`fix/review-phase1`、`fix/review-ub34-waveform`、`fix/single-stem-midi-output`、`fix/stem-analysis-workflow`、`fix/synthetic-audio-audit`、`fix/ui-ux-polish-v1`、`perf/live-output-callback` |
| **历史未合并分支（`design/*` / `feature/*` / `fix/*`）** | **8** | **主人逐一确认**（部分可能已通过 squash 合并或废弃） | `design/layout-review-20261117`（`+1`）、`design/realtime-analysis-review`（`+2`）、`feature/ab-zero-crossing`（`+2`）、`feature/chord-practice-midi-audition`（`+2`）、`feature/drum-audition`（`+3`）、`feature/drum-midi-export`（`+2`）、`feature/local-chord-practice`（`+2`）、`fix/help-hover-startup-flash-and-bootstrap`（`+3`） |

> 另注：仓库含 2 个备份 tag（`phase0-10-audit-backup`、`phase0-phase1-backup`），按 `AGENTS.md` 规则**保留**。
