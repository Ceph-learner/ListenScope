# ListenScope 应用图标（v1.1 精修版）

基于原图标（`ui/assets/listenscope.svg`）精修：构图、比例、配色与识别元素（倒角机箱、居中示波柱、十字标定、状态条、棋盘角标）全部保留，只提升质感与小尺寸可读性。

| 文件 | 用途 |
|---|---|
| `listenscope_master_dark.svg` | 主图标（暗色），用于 ≥40 px：.ico 的 40/48/64/96/128/256、窗口、关于页、社交预览 |
| `listenscope_master_light.svg` | 主图标（浅色主题、浅色背景场景） |
| `listenscope_small_dark.svg` | 小尺寸专用（3 根粗柱 + 加粗外框），用于 16/20/24/32 px：任务栏小图标、托盘、文件图标 |
| `listenscope_small_light.svg` | 小尺寸浅色版 |
| `listenscope_tray_white.svg` / `listenscope_tray_black.svg` | 托盘单色版（深色 / 浅色任务栏） |

## 质感处理（相对原版）
- 机箱：对角线渐变 + 内框斜面（左上暗、右下亮）+ 2–3% 透明度扫描线（小尺寸下自动消失）
- 示波柱：三段纵向渐变（亮—本色—暗）+ 顶部 2 px 高光 + 底部 2 px 阴影；峰值帽保持原位置
- 颜色与原版一致：lime `#CEFF18`、teal `#77DCE4`、green `#00A878`、底 `#0B0D0F`
- 全部为纯矢量，无滤镜、无模糊、无 QGraphicsEffect 依赖（符合项目 ZERO_GLOW 原则）

## 原创性
全部为项目内从零绘制的 SVG，未使用任何第三方图标或模板。比对结论见 `docs/design/ICON.md`（由 #42 E9 完成）。
