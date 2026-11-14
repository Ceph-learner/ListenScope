<#
.SYNOPSIS
    ListenScope Windows 隔离环境一键初始化脚本 (.venv-core + .venv-ai + 可选 .venv-midi).
.DESCRIPTION
    已结合 Windows 11 真机验收实测基线更新 (2026-11-14 第三轮):
      - Core 与 GPU AI 基线解释器: Python 3.12 x64 (实测 3.12.16)
      - AI GPU 实测组合与 cu128 约束:
          torch==2.11.0+cu128, torchaudio==2.11.0+cu128, torchvision==0.26.0+cu128
          (@ https://download.pytorch.org/whl/cu128)
          安装 requirements-ai.txt 时自动生成并传入 pip 约束文件 (-c / PIP_CONSTRAINT)，锁住已安装的
          +cu128 版本，防止 PyPI 在解析 torchvision 等传递依赖时替换已装的 CUDA PyTorch。
          同时安装 onnxruntime-gpu 1.26.0 (<1.27), audio-separator 0.48.0, demucs 4.1.0, audioread 3.1.0。
      - MIDI CPU 隔离环境 (.venv-midi): Python 3.11 x64 (实测 3.11.18) + basic-pitch 0.4.0 +
          tensorflow 2.15.0 + setuptools<81 + psutil + mido。
          注意: Windows 默认 LongPathsEnabled=0 下 TensorFlow 2.15 头文件层级较深，建议在短路径目录
          (如 E:\LS-midi) 下检出仓库，或通过 -MidiVenvPath E:\LS-midi\.venv-midi 指定短路径。

    目标真实硬件基线 (严禁误写为 16GB VRAM):
      - OS: Windows (Build >= 20348 for WASAPI Process Loopback)
      - GPU: NVIDIA GeForce RTX 5060 Ti (Blackwell, sm_120)
      - GPU 显存: 8GB VRAM
      - 系统内存: 16GB RAM

    结构说明:
      1) .venv-core: 轻量 GUI (PySide6 < 6.10) + WASAPI 捕获 + CPU 实时分析，禁止混入 PyTorch/CUDA。
      2) .venv-ai:   独立子进程 AI Worker (PyTorch cu128 三件套 + onnxruntime-gpu<1.27 + demucs + audio-separator + audioread)。
      3) .venv-midi: 独立子进程 CPU MIDI 转录 (Python 3.11 + basic-pitch + tensorflow<2.15.1 + setuptools<81)。
#>

[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [string]$CudaIndexUrl = "https://download.pytorch.org/whl/cu128",
    [string]$TorchSpec = "torch==2.11.0",
    [string]$TorchaudioSpec = "torchaudio==2.11.0",
    [string]$TorchvisionSpec = "torchvision==0.26.0",
    [string]$MidiPythonExe = "",
    [string]$MidiVenvPath = "",
    [switch]$SkipAI,
    [switch]$SkipMidi,
    [switch]$AllowUntestedPython
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
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

function Resolve-LauncherPython {
    param([string]$SpecVersion)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $resolved = & py "-$SpecVersion" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return ($resolved | Select-Object -First 1).Trim()
        }
    }
    return ""
}

function Test-PythonSpec {
    param(
        [string]$Exe,
        [int]$ExpectedMajor,
        [int]$ExpectedMinor
    )
    $info = & $Exe -c "import platform, sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{platform.architecture()[0]}')"
    if ($LASTEXITCODE -ne 0 -or -not $info) {
        throw "无法读取 Python 版本信息: $Exe"
    }
    $parts = ($info | Select-Object -First 1).Trim().Split("|")
    $ver = $parts[0]
    $arch = if ($parts.Length -gt 1) { $parts[1] } else { "unknown" }
    $verNums = $ver.Split(".")
    $maj = [int]$verNums[0]
    $min = [int]$verNums[1]
    return [PSCustomObject]@{
        Version = $ver
        Arch = $arch
        Matches = ($maj -eq $ExpectedMajor -and $min -eq $ExpectedMinor -and $arch -eq "64bit")
    }
}

if (-not $PythonExe) {
    $Auto312 = Resolve-LauncherPython -SpecVersion "3.12"
    if ($Auto312) {
        $PythonExe = $Auto312
        Write-Host "自动检测到 Python 3.12 x64: $PythonExe" -ForegroundColor Gray
    } else {
        $PythonExe = "python"
    }
}

$CorePyMeta = Test-PythonSpec -Exe $PythonExe -ExpectedMajor 3 -ExpectedMinor 12
if (-not $CorePyMeta.Matches) {
    $msg = "检测到 Core/AI Python 为 $($CorePyMeta.Version) ($($CorePyMeta.Arch))；实测基线为 Python 3.12 x64 (cu128 + onnxruntime-gpu 1.26.0)。"
    if (-not $AllowUntestedPython) {
        throw "$msg 请使用 `-PythonExe <Python3.12路径>`（例如 `-PythonExe C:\Python312\python.exe`），或显式加 `-AllowUntestedPython` 跳过版本校验。"
    }
    Write-Warning $msg
}

Write-Host "=== [1/3] 初始化 Core 桌面环境 (.venv-core) [$($CorePyMeta.Version) $($CorePyMeta.Arch)] ===" -ForegroundColor Green
$CoreVenv = Join-Path $RepoRoot ".venv-core"
$CorePy = Join-Path $CoreVenv "Scripts\python.exe"
if (-not (Test-Path $CorePy)) {
    Invoke-Checked $PythonExe @("-m", "venv", $CoreVenv)
}
Invoke-Checked $CorePy @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $CorePy @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements-windows.txt"))
Invoke-Checked $CorePy @("-m", "pip", "check")
Invoke-Checked $CorePy @("scripts\check_env.py", "--write-report", "SYSTEM_REPORT.md")

if (-not $SkipAI) {
    Write-Host "=== [2/3] 初始化隔离 RTX 5060 Ti AI Worker 环境 (.venv-ai) [$TorchSpec $TorchaudioSpec $TorchvisionSpec @ $CudaIndexUrl] ===" -ForegroundColor Green
    $AiVenv = Join-Path $RepoRoot ".venv-ai"
    $AiPy = Join-Path $AiVenv "Scripts\python.exe"
    if (-not (Test-Path $AiPy)) {
        Invoke-Checked $PythonExe @("-m", "venv", $AiVenv)
    }
    Invoke-Checked $AiPy @("-m", "pip", "install", "--upgrade", "pip")

    $TorchInstallArgs = @("-m", "pip", "install", $TorchSpec, $TorchaudioSpec)
    if ($TorchvisionSpec) {
        $TorchInstallArgs += $TorchvisionSpec
    }
    if ($CudaIndexUrl) {
        $TorchInstallArgs += @("--index-url", $CudaIndexUrl)
    }
    Invoke-Checked $AiPy $TorchInstallArgs

    # 读取已安装的 torch/torchaudio/torchvision 精确版本 (例如 2.11.0+cu128 / 0.26.0+cu128) 生成 pip 约束，
    # 防止后续从 PyPI 安装 requirements-ai.txt 时因解析 torchvision 等依赖而替换已安装的 cu128 PyTorch。
    $CudaConstraintFile = Join-Path $AiVenv "cuda-constraints.txt"
    $PinnedLines = & $AiPy -c "import importlib.metadata as m; pkgs=['torch','torchaudio','torchvision']; print('\n'.join(f'{p}=={m.version(p)}' for p in pkgs))"
    if ($LASTEXITCODE -ne 0 -or -not $PinnedLines) {
        throw "无法读取 .venv-ai 中已安装的 torch/torchaudio/torchvision 版本。"
    }
    $ConstraintContent = @($PinnedLines) + @("onnxruntime-gpu>=1.21.0,<1.27")
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($CudaConstraintFile, $ConstraintContent, $Utf8NoBom)
    Write-Host "[cu128 约束] 已写入 $CudaConstraintFile : $($ConstraintContent -join ', ')" -ForegroundColor Gray

    $PrevPipConstraint = $env:PIP_CONSTRAINT
    try {
        $env:PIP_CONSTRAINT = $CudaConstraintFile
        Invoke-Checked $AiPy @(
            "-m", "pip", "install",
            "-r", (Join-Path $RepoRoot "requirements-ai.txt"),
            "-c", $CudaConstraintFile
        )
    } finally {
        if ($null -eq $PrevPipConstraint) {
            Remove-Item Env:PIP_CONSTRAINT -ErrorAction SilentlyContinue
        } else {
            $env:PIP_CONSTRAINT = $PrevPipConstraint
        }
    }

    Invoke-Checked $AiPy @(
        "-c",
        "import torch, torchaudio, torchvision; assert '+cu' in torch.__version__, f'Expected CUDA torch build, got {torch.__version__}'; print('Verified cu128 stack:', torch.__version__, torchaudio.__version__, torchvision.__version__)"
    )
    Invoke-Checked $AiPy @("-m", "pip", "check")
    Invoke-Checked $AiPy @("scripts\check_env.py", "--json", "--check-ai-packages", "--write-report", "SYSTEM_REPORT.md")
}

# 检查 FFmpeg 查找位置 (PATH 或仓库本地路径)
$FfmpegFound = $null
$FfmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($FfmpegCmd) {
    $FfmpegFound = $FfmpegCmd.Source
} else {
    foreach ($cand in @(
        (Join-Path $RepoRoot "ffmpeg.exe"),
        (Join-Path $RepoRoot "ffmpeg\bin\ffmpeg.exe"),
        (Join-Path $RepoRoot "tools\ffmpeg\bin\ffmpeg.exe")
    )) {
        if (Test-Path $cand) {
            $FfmpegFound = $cand
            break
        }
    }
}
if ($FfmpegFound) {
    Write-Host "[FFmpeg] 已检测到: $FfmpegFound" -ForegroundColor Green
} else {
    Write-Warning "[FFmpeg] 未检测到 ffmpeg.exe。WAV 输入可走 soundfile，但部分解码/音频格式需 FFmpeg。建议执行 `winget install Gyan.FFmpeg` 或将 ffmpeg.exe 放入 PATH / 仓库根目录。"
}

$MidiReadyCreated = $false
$MidiPyResolved = ""
if (-not $SkipMidi) {
    if (-not $MidiPythonExe) {
        $MidiPythonExe = Resolve-LauncherPython -SpecVersion "3.11"
    }
    if ($MidiPythonExe) {
        $MidiPyMeta = Test-PythonSpec -Exe $MidiPythonExe -ExpectedMajor 3 -ExpectedMinor 11
        if (-not $MidiPyMeta.Matches -and -not $AllowUntestedPython) {
            Write-Warning "跳过 .venv-midi 创建：检测到的 MIDI 解释器为 $($MidiPyMeta.Version) ($($MidiPyMeta.Arch))，Basic Pitch + TensorFlow 2.15 需要 Python 3.11 x64。"
        } else {
            $MidiVenv = if ($MidiVenvPath) { $MidiVenvPath } else { Join-Path $RepoRoot ".venv-midi" }
            if ($MidiVenv.Length -gt 48) {
                Write-Warning "当前 .venv-midi 路径较长 ($($MidiVenv.Length) 字符: $MidiVenv)。若 Windows 未开启 LongPathsEnabled=1，TensorFlow 2.15 深度头文件可能触发 [Errno 2]；建议使用短路径目录 (如 E:\LS-midi) 或传入 -MidiVenvPath E:\LS-midi\.venv-midi。"
            }
            Write-Host "=== [3/3] 初始化隔离 CPU MIDI 环境 ($MidiVenv) [$($MidiPyMeta.Version) $($MidiPyMeta.Arch)] ===" -ForegroundColor Green
            $MidiPy = Join-Path $MidiVenv "Scripts\python.exe"
            if (-not (Test-Path $MidiPy)) {
                Invoke-Checked $MidiPythonExe @("-m", "venv", $MidiVenv)
            }
            Invoke-Checked $MidiPy @("-m", "pip", "install", "--upgrade", "pip")
            Invoke-Checked $MidiPy @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements-midi.txt"))
            Invoke-Checked $MidiPy @("-m", "pip", "check")
            Invoke-Checked $MidiPy @("scripts\check_env.py", "--json", "--check-midi-packages", "--no-write")
            $MidiReadyCreated = $true
            $MidiPyResolved = $MidiPy
        }
    } else {
        Write-Host "=== [3/3] 跳过 .venv-midi（未找到 Python 3.11 x64；GUI 将提示配置或走轻量单音回退） ===" -ForegroundColor Yellow
        Write-Host "如需启用 Spotify Basic Pitch CPU MIDI 转录，请先安装 Python 3.11 x64 后在短路径执行:" -ForegroundColor Yellow
        Write-Host "  pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -SkipAI -MidiPythonExe <Python3.11路径> -MidiVenvPath E:\LS-midi\.venv-midi" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "初始化完成！启动命令示例:" -ForegroundColor Green
Write-Host "  .\.venv-core\Scripts\python.exe capture_test.py --name QQMusic.exe --fallback-system"
if ($MidiReadyCreated) {
    Write-Host "  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python `"$MidiPyResolved`""
} else {
    Write-Host "  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe"
}
