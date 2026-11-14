<#
.SYNOPSIS
    ListenScope Windows 隔离环境一键初始化脚本 (.venv-core + .venv-ai + 可选 .venv-midi).
.DESCRIPTION
    已结合 Windows 11 真机验收实测基线更新 (2026-11-14 第四轮):
      - Core 与 GPU AI 基线解释器: Python 3.12 x64 (实测 3.12.16)
      - AI GPU 实测组合与 cu128 约束:
          torch==2.11.0+cu128, torchaudio==2.11.0+cu128, torchvision==0.26.0+cu128
          (@ https://download.pytorch.org/whl/cu128 或通过 -CudaWheelDir 优先使用本地已下载官方 wheel)
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
      1) .venv-core: 轻量 GUI (PySide6 < 6.10) + WASAPI 捕获 + winrt SMTC + CPU 实时分析，禁止混入 PyTorch/CUDA。
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
    [string]$CudaWheelDir = "",
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
        Major = $maj
        Minor = $min
        Matches = ($maj -eq $ExpectedMajor -and $min -eq $ExpectedMinor -and $arch -eq "64bit")
    }
}

function Resolve-LocalCudaWheel {
    param(
        [string]$WheelDir,
        [string]$PkgName,
        [string]$RequestedSpec,
        [string]$ExpectedCudaTag,
        [string]$ExpectedPyTag,
        [string]$ExpectedPlatTag,
        [switch]$SkipAbiStrict
    )
    if (-not $RequestedSpec) {
        return $null
    }
    if ($RequestedSpec -match "\.whl$" -and (Test-Path $RequestedSpec -PathType Leaf)) {
        return (Resolve-Path $RequestedSpec).Path
    }

    $ExpectedVerBase = ""
    if ($RequestedSpec -match "^[^=<>!~]+==([0-9A-Za-z._-]+?)(?:\+(cu[0-9]+))?$") {
        $ExpectedVerBase = $Matches[1]
        if ($Matches[2]) {
            $ExpectedCudaTag = $Matches[2]
        }
    }

    $NormTargetPkg = $PkgName.ToLowerInvariant().Replace("-", "_")
    $Candidates = Get-ChildItem -Path $WheelDir -Filter "*.whl" -File | Sort-Object Name
    $MismatchReasons = @()

    foreach ($Whl in $Candidates) {
        $BaseNoExt = [System.IO.Path]::GetFileNameWithoutExtension($Whl.Name)
        $Parts = $BaseNoExt.Split("-")
        if ($Parts.Length -lt 5) {
            continue
        }
        $WhlPkg = $Parts[0].ToLowerInvariant().Replace("-", "_")
        if ($WhlPkg -ne $NormTargetPkg) {
            continue
        }

        if ($Whl.Name -match "%2[Bb]") {
            throw "检测到 URL 编码文件名 '$($Whl.Name)'（含 %2B）；pip 不接受含 %2B 的本地 wheel 文件名。请将 %2B 重命名为 '+' 后重试（例如 torch-2.11.0+cu128-...whl）。"
        }

        $WhlVer = $Parts[1]
        $WhlPyTag = $Parts[$Parts.Length - 3].ToLowerInvariant()
        $WhlPlatTag = $Parts[$Parts.Length - 1].ToLowerInvariant()

        $WhlVerBase = $WhlVer
        $WhlCudaTag = ""
        if ($WhlVer -match "^([^\+]+)\+(.+)$") {
            $WhlVerBase = $Matches[1]
            $WhlCudaTag = $Matches[2].ToLowerInvariant()
        }

        if ($ExpectedVerBase -and ($WhlVerBase -ne $ExpectedVerBase)) {
            $MismatchReasons += "$($Whl.Name): 版本=$WhlVerBase（期望 $ExpectedVerBase）"
            continue
        }
        if ($ExpectedCudaTag -and ($WhlCudaTag -ne $ExpectedCudaTag.ToLowerInvariant())) {
            $MismatchReasons += "$($Whl.Name): CUDA标识='$WhlCudaTag'（期望 '+$ExpectedCudaTag'）"
            continue
        }
        if (-not $SkipAbiStrict) {
            if ($ExpectedPyTag -and ($WhlPyTag -ne $ExpectedPyTag.ToLowerInvariant()) -and ($WhlPyTag -ne "py3")) {
                $MismatchReasons += "$($Whl.Name): Python标签=$WhlPyTag（期望 $ExpectedPyTag）"
                continue
            }
            if ($ExpectedPlatTag -and ($WhlPlatTag -ne $ExpectedPlatTag.ToLowerInvariant()) -and ($WhlPlatTag -ne "any")) {
                $MismatchReasons += "$($Whl.Name): 平台=$WhlPlatTag（期望 $ExpectedPlatTag）"
                continue
            }
        }
        return $Whl.FullName
    }

    if ($MismatchReasons.Count -gt 0) {
        throw "在 -CudaWheelDir '$WheelDir' 中发现 '$PkgName' 的 wheel，但版本/CUDA/Python/平台不匹配: $($MismatchReasons -join '; ')"
    }
    return $null
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
    $ExpectedCudaTag = "cu128"
    if ($CudaIndexUrl -and ($CudaIndexUrl -match "(cu[0-9]+)$")) {
        $ExpectedCudaTag = $Matches[1].ToLowerInvariant()
    }
    $ExpectedPyTag = "cp$($CorePyMeta.Major)$($CorePyMeta.Minor)"
    $ExpectedPlatTag = "win_amd64"

    $AiVenv = Join-Path $RepoRoot ".venv-ai"
    $AiPy = Join-Path $AiVenv "Scripts\python.exe"
    if (-not (Test-Path $AiPy)) {
        Invoke-Checked $PythonExe @("-m", "venv", $AiVenv)
    }
    Invoke-Checked $AiPy @("-m", "pip", "install", "--upgrade", "pip")

    $ResolvedCudaWheelDir = ""
    if ($CudaWheelDir) {
        if (-not (Test-Path $CudaWheelDir -PathType Container)) {
            throw "指定的 -CudaWheelDir 目录不存在: $CudaWheelDir"
        }
        $ResolvedCudaWheelDir = (Resolve-Path $CudaWheelDir).Path
    }

    $PackageJobs = @(
        @{ Name = "torch"; Spec = $TorchSpec },
        @{ Name = "torchaudio"; Spec = $TorchaudioSpec },
        @{ Name = "torchvision"; Spec = $TorchvisionSpec }
    )

    if ($ResolvedCudaWheelDir) {
        Write-Host "=== [2/3] 初始化隔离 RTX 5060 Ti AI Worker 环境 (.venv-ai) [优先本地 wheel: $ResolvedCudaWheelDir] ===" -ForegroundColor Green
        $LocalWheels = @()
        $MissingOnlineSpecs = @()
        foreach ($Item in $PackageJobs) {
            if (-not $Item.Spec) {
                continue
            }
            $MatchedWhl = Resolve-LocalCudaWheel `
                -WheelDir $ResolvedCudaWheelDir `
                -PkgName $Item.Name `
                -RequestedSpec $Item.Spec `
                -ExpectedCudaTag $ExpectedCudaTag `
                -ExpectedPyTag $ExpectedPyTag `
                -ExpectedPlatTag $ExpectedPlatTag `
                -SkipAbiStrict:$AllowUntestedPython
            if ($MatchedWhl) {
                $LocalWheels += $MatchedWhl
            } else {
                $MissingOnlineSpecs += $Item.Spec
            }
        }

        if ($LocalWheels.Count -eq 0) {
            throw "在 -CudaWheelDir '$ResolvedCudaWheelDir' 中未找到任何匹配的 $ExpectedCudaTag wheel（需要 $TorchSpec / $TorchaudioSpec / $TorchvisionSpec 的 +$ExpectedCudaTag, $ExpectedPyTag, $ExpectedPlatTag 文件）。如仅需在线安装，请移除 -CudaWheelDir。"
        }

        Write-Host "[cu128 本地 wheel 优先] 命中 $($LocalWheels.Count) 个本地 wheel:" -ForegroundColor Green
        foreach ($WhlPath in $LocalWheels) {
            Write-Host "  - $WhlPath" -ForegroundColor Green
        }

        $TorchInstallArgs = @("-m", "pip", "install", "--find-links", $ResolvedCudaWheelDir) + $LocalWheels
        if ($MissingOnlineSpecs.Count -gt 0) {
            Write-Warning "下列包未在 $ResolvedCudaWheelDir 中找到本地 wheel，将回退到 $CudaIndexUrl 在线获取: $($MissingOnlineSpecs -join ', ')"
            $TorchInstallArgs += $MissingOnlineSpecs
            if ($CudaIndexUrl) {
                $TorchInstallArgs += @("--index-url", $CudaIndexUrl)
            }
        } else {
            Write-Host "[cu128 本地 wheel 优先] torch/torchaudio/torchvision 全部从本地 wheel 安装（传递纯 Python 依赖优先复用 $ResolvedCudaWheelDir，缺项将按需联网获取）。" -ForegroundColor Gray
        }
        Invoke-Checked $AiPy $TorchInstallArgs
    } else {
        Write-Host "=== [2/3] 初始化隔离 RTX 5060 Ti AI Worker 环境 (.venv-ai) [$TorchSpec $TorchaudioSpec $TorchvisionSpec @ $CudaIndexUrl] ===" -ForegroundColor Green
        $TorchInstallArgs = @("-m", "pip", "install", $TorchSpec, $TorchaudioSpec)
        if ($TorchvisionSpec) {
            $TorchInstallArgs += $TorchvisionSpec
        }
        if ($CudaIndexUrl) {
            $TorchInstallArgs += @("--index-url", $CudaIndexUrl)
        }
        try {
            Invoke-Checked $AiPy $TorchInstallArgs
        } catch {
            Write-Warning "在线安装 CUDA PyTorch 失败。若遇到 2.75 GB cu128 wheel 下载停滞/超时，可先将官方匹配 wheel 下载到本地目录后传入 `-CudaWheelDir <目录>` 重试（详见 docs\PACKAGING.md）。"
            throw
        }
    }

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

    $CudaSuffixCheck = if ($ExpectedCudaTag) { "+$ExpectedCudaTag" } else { "+cu" }
    Invoke-Checked $AiPy @(
        "-c",
        "import torch, torchaudio, torchvision; exp='$CudaSuffixCheck'; assert all(exp in str(v) for v in (torch.__version__, torchaudio.__version__, torchvision.__version__)), f'Expected {exp} stack, got torch={torch.__version__}, torchaudio={torchaudio.__version__}, torchvision={torchvision.__version__}'; print('Verified CUDA stack:', torch.__version__, torchaudio.__version__, torchvision.__version__)"
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
