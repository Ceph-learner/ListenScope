# ListenScope 设计规范与 Design Tokens

本文件记录 ListenScope 桌面端 UI 的排版尺度、字体栈、明暗配色 token 与组件状态约定。

## 1. 间距尺度（Spacing Scale）
- **Token 序列**：`4/8/12/16/24/32` px
  - `4 px`：控件内部图标与文字间距、紧凑分段按钮间隙
  - `8 px`：工具栏控件组间距、卡片内小行距
  - `12 px`：卡片内边距、分栏间距
  - `16 px`：区块间距、设置页分组间距
  - `24 px`：页面主区段分隔、状态栏固定高度
  - `32 px`：大屏留白与空状态引导卡外边距

## 2. 圆角尺度（Border Radius）
- **Token 序列**：`0/2/4` px
  - `0 px`：Acid Telemetry 预设（直角机械仪表风格）
  - `2 px`：小徽章、5 格稳定度条、状态指示块
  - `4 px`：标准主题按钮、输入框、下拉框、卡片容器

## 3. 字号尺度（Type Scale）
- **Token 序列**：`11/12/13/16/20/28` px
  - `11 px`：微标签、坐标轴刻度、状态栏遥测文字
  - `12 px`：正文、按钮、表格单元格（默认基准字号）
  - `13 px`：分组标题、次级标签页标题
  - `16 px`：卡片标题、对话框小节标题
  - `20 px`：次级主指标（如调性、BPM）
  - `28 px`：主识别指标（如实时主和弦名）

## 4. 字体栈（不随应用打包任何字体）
- **UI 正文 / CJK**：`"Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC", sans-serif`
- **等宽遥测 / 坐标轴**：`"Cascadia Mono", "Consolas", "Noto Sans Mono CJK SC", monospace`

## 5. 明暗颜色 Tokens

| Token | 浅色模式 (Light) | 暗色模式 (Dark) | 用途 |
|---|---|---|---|
| `bg_canvas` | `#F6F8FA` / `#F1F2EC` | `#14161A` / `#0B0D0F` | 主窗口画布底色 |
| `bg_surface` | `#FFFFFF` / `#E6E8E0` | `#1C2026` / `#14181D` | 卡片与面板底色 |
| `border_rim` | `#CBD5E1` / `#9CA3AF` | `#2C323C` / `#2A313B` | 1 px 边框与分割线 |
| `fg_primary` | `#0F172A` / `#090D10` | `#E6EAF0` / `#F1F2EC` | 主文字（对比度 ≥ 7:1） |
| `fg_subtle` | `#475569` | `#B4BECB` | 次要说明与坐标轴（对比度 ≥ 3:1） |
| `accent_primary` | `#00A878` | `#CEFF18` / `#7EE2B8` | 唯一实心主按钮（开始捕获等） |
| `danger` | `#C42B1C` / `#DC2626` | `#E03E3E` / `#FF3355` | 紧急停止（仅 AI 运行时亮红）、关闭悬停 |

## 6. 组件状态规范
- **主按钮**：每视图最多 1 个实心强调色主按钮，其余采用中性描边或透明底。
- **E-STOP**：始终固定在顶栏右侧且支持键盘聚焦与 `Ctrl+Shift+E`；AI 空闲时呈中性描边，AI 运行时切换为红底白字。
- **窗口控制按钮**：`46×32` px，使用 Lucide SVG 图标（`minus`、`square`/`copy`、`x`），关闭按钮悬停 `#C42B1C`。
- **可复用图标**：统一使用 `ui/assets/icons/` 下的 Lucide SVG（`lucide-static` v1.78.0，见 `ICONS.md`）。
- **设计预览表**：运行 `python scripts/make_screenshots.py --design-sheet` 可离线生成组件与 Token 预览图。
