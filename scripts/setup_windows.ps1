<#
.SYNOPSIS
    ListenScope Windows 双环境一键初始化脚本 (.venv-core + .venv-ai).
.DESCRIPTION
    未在 Windows 真机实际验证 (Scaffold generated from Linux; must be tested on physical Windows host).

    目标真实硬件基线 (严禁误写为 16GB VRAM):
      - OS: Windows 10/11 (20H1+, Build >= 19041)
      - GPU: NVIDIA GeForce RTX 5060 Ti (Blackwell, sm_120)
      - GPU 显存: 8GB VRAM
      - 系统内存: 16GB RAM

    结构说明:
      1) .venv-core: 轻量 GUI (PySide6 < 6.10) + WASAPI 捕获 + CPU 实时分析，禁止混入 PyTorch/CUDA。
      2) .venv-ai:   独立子进程 AI Worker (PyTorch CUDA >= 12.8 sm_120 + onnxruntime-gpu + demucs + audio-separator + basic-pitch)。
#>

[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [string]$CudaIndexUrl = "https://download.pytorch.org/whl/cu128",
    [switch]$SkipAI
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Invoke-Checked {
    param(
        [string]$Exe,
        [string[]]$ArgsList
    )
    Write-Host ">>> $Exe $($ArgsList -join ' ')" -ForegroundColor Cyan
    & $Exe @ArgsList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Exe $($ArgsList -join ' ')"
    }
}

Write-Host "=== [1/2] 初始化 Core 桌面环境 (.venv-core) ===" -ForegroundColor Green
$CoreVenv = Join-Path $RepoRoot ".venv-core"
$CorePy = Join-Path $CoreVenv "Scripts\python.exe"
if (-not (Test-Path $CorePy)) {
    Invoke-Checked $PythonExe @("-m", "venv", $CoreVenv)
}
Invoke-Checked $CorePy @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $CorePy @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements-windows.txt"))
Invoke-Checked $CorePy @("scripts\check_env.py", "--write-report", "SYSTEM_REPORT.md")

if (-not $SkipAI) {
    Write-Host "=== [2/2] 初始化隔离 RTX 5060 Ti AI Worker 环境 (.venv-ai) ===" -ForegroundColor Green
    $AiVenv = Join-Path $RepoRoot ".venv-ai"
    $AiPy = Join-Path $AiVenv "Scripts\python.exe"
    if (-not (Test-Path $AiPy)) {
        Invoke-Checked $PythonExe @("-m", "venv", $AiVenv)
    }
    Invoke-Checked $AiPy @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $AiPy @("-m", "pip", "install", "torch", "torchaudio", "--index-url", $CudaIndexUrl)
    Invoke-Checked $AiPy @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements-ai.txt"))
    Invoke-Checked $AiPy @("scripts\check_env.py", "--json", "--check-ai-packages", "--write-report", "SYSTEM_REPORT.md")
}

Write-Host ""
Write-Host "初始化完成！启动命令示例:" -ForegroundColor Green
Write-Host "  .\.venv-core\Scripts\python.exe capture_test.py --name QQMusic.exe --fallback-system"
Write-Host "  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe"
