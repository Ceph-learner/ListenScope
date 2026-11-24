# GitHub 仓库网页设置操作指南（REPO_SETTINGS_GUIDE）

> 本文档对应 Issue #37 `R3-8` 与 `R5-4`，供仓库主人（`@Ceph-learner`）在 GitHub 网页端逐项核对并执行。**AI 未修改任何远程仓库设置。**

---

## 1. About 与 Topics（仓库首页右侧齿轮图标）

1. 打开仓库首页 `https://github.com/Ceph-learner/ListenScope`，点击右上角 **About** 旁的齿轮图标（⚙️）。
2. **Description**（≤ 350 字符，中英各一句）：
   ```text
   免费离线本地 Windows 听歌分析、A/B 慢放与 AI 分轨扒谱工具 | Free, offline, local-first Windows music analysis, A/B looping & AI stem transcription workbench.
   ```
3. **Topics**（逐个填入并回车）：
   `music` `ear-training` `music-transcription` `bass` `chord-recognition` `key-detection` `audio-analysis` `stem-separation` `wasapi` `pyside6` `windows` `local-first`
4. 点击 **Save changes**。

---

## 2. 上传社交预览图（Social Preview）

1. 进入仓库 **Settings → General → Social preview**。
2. 点击 **Edit → Upload an image...**。
3. 上传 `feature/ui-polish-p2e`（#42 合并后位于 `main`）中的 `docs/design/social_preview.png`（1280×640）。

---

## 3. 开启 Discussions 并配置分类

1. 进入仓库 **Settings → General → Features**，勾选 **Discussions**。
2. 点击 **Set up discussions** 或进入仓库顶部 **Discussions** 标签页，确保保留/创建以下分类：
   - **Q&A**（问答格式，用于使用疑问）
   - **Ideas**（功能建议与讨论）
   - **Show & tell**（扒谱成果与配置分享）

---

## 4. `main` 分支保护规则（Branch Protection）

1. 进入仓库 **Settings → Branches → Add branch protection rule**（或 **Rules → Rulesets**）。
2. Branch name pattern 填写：`main`。
3. 勾选以下规则：
   - **Require a pull request before merging**（必须走 PR）。
   - **Require status checks to pass before merging**，并添加 CI 检查（如 `tests`）。
   - **Do not allow bypassing the above settings**（建议勾选，视个人工作流而定）。
   - 确保 **Allow force pushes** **保持未勾选**（禁止 force push）且 **Allow deletions** **保持未勾选**。
4. 点击 **Create / Save changes**。

---

## 5. 安全与扫描设置（Code Security）

进入仓库 **Settings → Code security**（部分选项需仓库设为 Public 后或免费版可用）：

1. **Private vulnerability reporting（私密漏洞报告）**：点击 **Enable**（与 `SECURITY.md` 对应）。
2. **Dependabot alerts** 与 **Dependabot security updates**：点击 **Enable**（配合 `.github/dependabot.yml`）。
3. **Secret scanning** 与 **Push protection**：在可用时点击 **Enable**，防止误推密钥/凭据。

---

## 6. 个人邮箱隐私设置（对应 R1-11）

1. 点击 GitHub 右上角头像 → **Settings → Emails**。
2. 勾选 **Keep my email addresses private** 与 **Block command line pushes that expose my email**。
3. 本机 Git 配置建议设为：`353659952+Ceph-learner@users.noreply.github.com`。
