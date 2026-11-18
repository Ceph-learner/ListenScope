<#
.SYNOPSIS
    ListenScope Windows PyInstaller Core 可执行目录与一键安装版 (Inno Setup 6) 构建脚本.
.DESCRIPTION
    未在 Windows 真机实际验证 (Scaffold authored from Linux; must be built & verified on Windows host).

    核心架构不变：
      - Core (`dist\ListenScopeCore\ListenScope.exe`) 仅含轻量 PySide6 GUI + WASAPI 捕获 + CPU 实时分析；
      - 显式排除 PyTorch/CUDA/ORT/TF，保证 Core 主进程内存安全；
      - 支持可选 `-BundleRuntimes` / `-BundleFfmpeg` 将已准备好的可迁移独立 Python 运行时
        (`runtime\ai` 与短路径 `m`) 及 `tools\ffmpeg` 一并放入输出目录；
      - 支持可选 `-BuildInstaller` 调用 Inno Setup 6 (`ISCC.exe`) 编译单文件安装包
        `dist\installer\ListenScope-Setup-Windows-x64.exe`。
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$BundleRuntimes,
    [switch]$BundleFfmpeg,
    [switch]$BuildInstaller,
    [string]$AiRuntimeDir = "",
    [string]$MidiRuntimeDir = "",
    [string]$FfmpegDir = "",
    [string]$IsccPath = "",
    [switch]$AllowMachineBoundVenv
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Assert-PortableRuntime {
    param(
        [string]$RuntimeDir,
        [string]$Label,
        [switch]$AllowVenvCfg
    )
    $Cfg = Join-Path $RuntimeDir "pyvenv.cfg"
    if ((Test-Path $Cfg) -and (-not $AllowVenvCfg)) {
        throw "[$Label] '$RuntimeDir' 检测到 venv 生成的 pyvenv.cfg，包含构建机本机绝对路径，复制到其他用户电脑会无法启动！请打包独立的 Python Embeddable/Standalone 目录（使 python.exe + Lib + DLLs + site-packages 自包含），或在本机测试时加 `-AllowMachineBoundVenv`。"
    }
}

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

$OutDir = Join-Path $RepoRoot "dist\ListenScopeCore"
$OutExe = Join-Path $OutDir "ListenScope.exe"
if (-not (Test-Path $OutExe)) {
    throw "打包完成但未找到输出可执行文件: $OutExe"
}

if ($BundleRuntimes) {
    $AiSrc = if ($AiRuntimeDir) { $AiRuntimeDir } else {
        @(
            (Join-Path $RepoRoot "staging\runtime\ai"),
            (Join-Path $RepoRoot "runtime\ai"),
            (Join-Path $RepoRoot ".venv-ai")
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($AiSrc) {
        Assert-PortableRuntime -RuntimeDir $AiSrc -Label "AI Runtime" -AllowVenvCfg:$AllowMachineBoundVenv
        $AiDst = Join-Path $OutDir "runtime\ai"
        if (Test-Path $AiDst) { Remove-Item -Recurse -Force $AiDst }
        New-Item -ItemType Directory -Force -Path (Split-Path $AiDst -Parent) | Out-Null
        Write-Host ">>> 内置 AI Runtime -> $AiDst (源: $AiSrc)" -ForegroundColor Cyan
        Copy-Item -Path $AiSrc -Destination $AiDst -Recurse -Force
    } else {
        Write-Warning "未找到可内置的 AI Runtime（staging\runtime\ai / runtime\ai / .venv-ai），安装版将依赖用户首次在设置中一键安装或手动配置。"
    }

    $MidiSrc = if ($MidiRuntimeDir) { $MidiRuntimeDir } else {
        @(
            (Join-Path $RepoRoot "staging\m"),
            (Join-Path $RepoRoot "m"),
            (Join-Path $RepoRoot "runtime\midi"),
            (Join-Path $RepoRoot ".venv-midi"),
            "D:\LS-midi\.venv-midi",
            "E:\LS-midi\.venv-midi",
            "C:\LS-midi\.venv-midi"
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($MidiSrc) {
        Assert-PortableRuntime -RuntimeDir $MidiSrc -Label "MIDI Runtime" -AllowVenvCfg:$AllowMachineBoundVenv
        # 使用超短路径 `{app}\m`，避免 TensorFlow 2.15 在 Windows MAX_PATH 下触发路径截断
        $MidiDst = Join-Path $OutDir "m"
        if (Test-Path $MidiDst) { Remove-Item -Recurse -Force $MidiDst }
        Write-Host ">>> 内置短路径 MIDI Runtime -> $MidiDst (源: $MidiSrc)" -ForegroundColor Cyan
        Copy-Item -Path $MidiSrc -Destination $MidiDst -Recurse -Force
    } else {
        Write-Warning "未找到可内置的 MIDI Runtime（staging\m / .venv-midi / D:\LS-midi\.venv-midi）。"
    }
}

if ($BundleFfmpeg) {
    $FfSrc = if ($FfmpegDir) { $FfmpegDir } else {
        @(
            (Join-Path $RepoRoot "tools\ffmpeg\bin"),
            (Join-Path $RepoRoot "ffmpeg\bin")
        ) | Where-Object { Test-Path (Join-Path $_ "ffmpeg.exe") } | Select-Object -First 1
    }
    if ($FfSrc) {
        $FfDst = Join-Path $OutDir "tools\ffmpeg\bin"
        New-Item -ItemType Directory -Force -Path $FfDst | Out-Null
        Write-Host ">>> 内置 FFmpeg -> $FfDst (源: $FfSrc)" -ForegroundColor Cyan
        Copy-Item -Path (Join-Path $FfSrc "*") -Destination $FfDst -Recurse -Force
    } else {
        Write-Warning "未找到 tools\ffmpeg\bin\ffmpeg.exe，跳过 FFmpeg 内置。"
    }
}

if ($BuildInstaller) {
    if (-not $IsccPath) {
        $Cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($Cmd) {
            $IsccPath = $Cmd.Source
        } else {
            $IsccPath = @(
                "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
            ) | Where-Object { Test-Path $_ } | Select-Object -First 1
        }
    }
    if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
        throw "未找到 Inno Setup 6 编译器 (ISCC.exe)。请安装 Inno Setup 6 或传入 -IsccPath。"
    }
    $IssFile = Join-Path $RepoRoot "scripts\installer.iss"
    Write-Host ">>> 运行 Inno Setup 6 编译安装包: $IsccPath $IssFile" -ForegroundColor Cyan
    & $IsccPath $IssFile
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC 编译安装包失败 (exit code=$LASTEXITCODE)"
    }
    Write-Host "✅ 安装包已生成: $(Join-Path $RepoRoot 'dist\installer\ListenScope-Setup-Windows-x64.exe')" -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ 构建流程完成: $OutExe" -ForegroundColor Green
