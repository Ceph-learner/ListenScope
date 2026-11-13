<#
.SYNOPSIS
    ListenScope Windows PyInstaller Core 可执行目录打包脚本.
.DESCRIPTION
    未在 Windows 真机实际验证 (Scaffold generated from Linux; must be built & tested on Windows host).

    仅打包轻量 Core GUI + CPU 分析 + WASAPI 捕获；CUDA / PyTorch / Demucs / Basic Pitch 显式排除，
    通过设置页或 `--ai-python` 指向外部 `.venv-ai\Scripts\python.exe` 运行以守住主进程 <1GB RAM 目标。
#>

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$CorePy = Join-Path $RepoRoot ".venv-core\Scripts\python.exe"
if (-not (Test-Path $CorePy)) {
    throw "未找到 .venv-core\Scripts\python.exe，请先运行 .\scripts\setup_windows.ps1"
}

Write-Host ">>> 安装 / 确认 PyInstaller" -ForegroundColor Cyan
& $CorePy -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 安装失败 (exit code=$LASTEXITCODE)"
}

$PyInstallerArgs = @("-m", "PyInstaller", "packaging\listenscope_core.spec", "--noconfirm")
if ($Clean) {
    $PyInstallerArgs += "--clean"
}

Write-Host ">>> 运行 PyInstaller 打包 Core: $CorePy $($PyInstallerArgs -join ' ')" -ForegroundColor Cyan
& $CorePy @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败 (exit code=$LASTEXITCODE)"
}

$OutExe = Join-Path $RepoRoot "dist\ListenScopeCore\ListenScope.exe"
if (-not (Test-Path $OutExe)) {
    throw "打包完成但未找到输出可执行文件: $OutExe"
}

Write-Host ""
Write-Host "✅ Core 打包完成: $OutExe" -ForegroundColor Green
Write-Host "提示: 首次运行可在 [设置 -> 资源安全阈值 & AI 配置] 选择 .venv-ai\Scripts\python.exe 并点击 [验证 AI 环境]。"
