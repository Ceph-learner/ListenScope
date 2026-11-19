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
    [string]$AiVenvPath = "",
    [string]$MidiPythonExe = "",
    [string]$MidiVenvPath = "",
    [switch]$SkipCore,
    [switch]$SkipAI,
    [switch]$SkipMidi,
    [switch]$AllowUntestedPython,
    [switch]$CheckCudaWheels,
    [switch]$AutoInstallPython
)

$ErrorActionPreference = "Stop"
$ErrorView = "NormalView"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:NO_COLOR = "1"
if (Get-Variable -Name PSStyle -ErrorAction SilentlyContinue) {
    $PSStyle.OutputRendering = "PlainText"
}
$Utf8NoBomConsole = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBomConsole
try {
    if (-not [Console]::IsInputRedirected) {
        [Console]::InputEncoding = $Utf8NoBomConsole
    }
    [Console]::OutputEncoding = $Utf8NoBomConsole
} catch {
}

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

function Test-PythonSpec {
    param(
        [string]$Exe,
        [int]$ExpectedMajor,
        [int]$ExpectedMinor
    )
    $info = & $Exe -c "import platform, sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{platform.architecture()[0]}')" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $info) {
        throw "无法读取 Python 版本信息: $Exe"
    }
    $parts = ($info | Select-Object -First 1).ToString().Trim().Split("|")
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

function Test-PythonCandidateMatch {
    param(
        [string]$Exe,
        [int]$ExpectedMajor,
        [int]$ExpectedMinor
    )
    if (-not $Exe) {
        return $false
    }
    try {
        $meta = Test-PythonSpec -Exe $Exe -ExpectedMajor $ExpectedMajor -ExpectedMinor $ExpectedMinor
        return [bool]$meta.Matches
    } catch {
        return $false
    }
}

function Resolve-LauncherPython {
    param([string]$SpecVersion)
    $specParts = $SpecVersion.Split(".")
    if ($specParts.Length -lt 2) {
        return ""
    }
    $targetMaj = [int]$specParts[0]
    $targetMin = [int]$specParts[1]
    $compactTag = "$targetMaj$targetMin"
    $candidates = New-Object System.Collections.Generic.List[string]

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $resolved = & py "-$SpecVersion" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                $candidates.Add(($resolved | Select-Object -First 1).ToString().Trim())
            }
        } catch {
        }
        try {
            $listOut = & py -0p 2>$null
            if ($LASTEXITCODE -eq 0 -and $listOut) {
                foreach ($line in $listOut) {
                    $txt = $line.ToString().Trim()
                    if ($txt -match "(?i)([A-Za-z]:\\[^\r\n]*python\.exe)\s*$") {
                        $candidates.Add($Matches[1].Trim())
                    }
                }
            }
        } catch {
        }
    }

    foreach ($regRoot in @(
        "HKCU:\Software\Python\PythonCore",
        "HKLM:\SOFTWARE\Python\PythonCore",
        "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore"
    )) {
        if (Test-Path -LiteralPath $regRoot) {
            try {
                Get-ChildItem -LiteralPath $regRoot -ErrorAction SilentlyContinue | ForEach-Object {
                    $installKey = Join-Path $_.PSPath "InstallPath"
                    if (Test-Path -LiteralPath $installKey) {
                        $props = Get-ItemProperty -LiteralPath $installKey -ErrorAction SilentlyContinue
                        if ($props) {
                            $exeProp = $props.PSObject.Properties["ExecutablePath"]
                            if ($exeProp -and $exeProp.Value) {
                                $candidates.Add($exeProp.Value.ToString().Trim())
                            }
                            $defProp = $props.PSObject.Properties["(default)"]
                            if ($defProp -and $defProp.Value) {
                                $candidates.Add((Join-Path $defProp.Value.ToString().Trim() "python.exe"))
                            }
                        }
                    }
                }
            } catch {
            }
        }
    }

    $dirPatterns = @()
    if ($env:LOCALAPPDATA) {
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$compactTag\python.exe")
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe")
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "Python\pythoncore-$SpecVersion*\python.exe")
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "Python\bin\python$SpecVersion*.exe")
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "uv\python\cpython-$SpecVersion*\python.exe")
        $dirPatterns += (Join-Path $env:LOCALAPPDATA "uv\python\cpython-$SpecVersion*\install\python.exe")
    }
    if ($env:ProgramFiles) {
        $dirPatterns += (Join-Path $env:ProgramFiles "Python$compactTag\python.exe")
        $dirPatterns += (Join-Path $env:ProgramFiles "Python*\python.exe")
    }
    foreach ($driveRoot in @("C:\", "D:\", "E:\")) {
        $dirPatterns += (Join-Path $driveRoot "Python$compactTag\python.exe")
        $dirPatterns += (Join-Path $driveRoot "Python$compactTag-64\python.exe")
    }
    $condaRoots = @()
    if ($env:USERPROFILE) {
        $condaRoots += (Join-Path $env:USERPROFILE "miniconda3")
        $condaRoots += (Join-Path $env:USERPROFILE "anaconda3")
    }
    if ($env:LOCALAPPDATA) {
        $condaRoots += (Join-Path $env:LOCALAPPDATA "miniconda3")
        $condaRoots += (Join-Path $env:LOCALAPPDATA "anaconda3")
    }
    $condaRoots += @("C:\ProgramData\miniconda3", "C:\ProgramData\anaconda3", "D:\miniconda3", "D:\anaconda3")
    foreach ($cRoot in $condaRoots) {
        $dirPatterns += (Join-Path $cRoot "python.exe")
        $dirPatterns += (Join-Path $cRoot "envs\*\python.exe")
    }
    foreach ($pat in $dirPatterns) {
        try {
            Get-Item -Path $pat -ErrorAction SilentlyContinue | ForEach-Object {
                $candidates.Add($_.FullName)
            }
        } catch {
        }
    }

    foreach ($cmdName in @("python$SpecVersion", "python3", "python")) {
        $cmdObj = Get-Command $cmdName -ErrorAction SilentlyContinue
        if ($cmdObj -and $cmdObj.Source) {
            $candidates.Add($cmdObj.Source)
        }
    }

    $seen = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($cand in $candidates) {
        if (-not $cand) {
            continue
        }
        if (-not (Test-Path -LiteralPath $cand -PathType Leaf)) {
            continue
        }
        if ($cand -like "*\WindowsApps\python*.exe") {
            continue
        }
        $resolvedCand = (Resolve-Path -LiteralPath $cand -ErrorAction SilentlyContinue)
        $candPath = if ($resolvedCand) { $resolvedCand.Path } else { $cand }
        if ($seen.Add($candPath)) {
            if (Test-PythonCandidateMatch -Exe $candPath -ExpectedMajor $targetMaj -ExpectedMinor $targetMin) {
                return $candPath
            }
        }
    }
    return ""
}

function Install-PythonViaWinget {
    param([string]$SpecVersion)
    $WingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $WingetCmd) {
        return ""
    }
    $PkgId = switch ($SpecVersion) {
        "3.12" { "Python.Python.3.12" }
        "3.11" { "Python.Python.3.11" }
        default { "" }
    }
    if (-not $PkgId) {
        return ""
    }
    Write-Host "未检测到 Python $SpecVersion x64，正在尝试通过 winget 自动安装 ($PkgId)..." -ForegroundColor Yellow
    & $WingetCmd.Source install --id $PkgId -e --source winget --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget 安装 $PkgId 返回退出码 $LASTEXITCODE。"
    }
    return (Resolve-LauncherPython -SpecVersion $SpecVersion)
}

function Resolve-LocalCudaWheel {
    param(
        [string]$WheelDir,
        [string]$PkgName,
        [string]$RequestedSpec,
        [string]$ExpectedCudaTag,
        [string]$ExpectedPyTag,
        [string]$ExpectedPlatTag,
        [switch]$SkipAbiStrict,
        [switch]$CheckBaseline
    )
    if (-not $RequestedSpec) {
        return $null
    }
    $ExpectedVerBase = ""
    if ($RequestedSpec -match "^[^=<>!~]+==([0-9A-Za-z._-]+?)(?:\+(cu[0-9]+))?$") {
        $ExpectedVerBase = $Matches[1]
        if ($Matches[2]) {
            $ExpectedCudaTag = $Matches[2]
        }
    }

    $NormTargetPkg = $PkgName.ToLowerInvariant().Replace("-", "_")
    $ExplicitWheel = $RequestedSpec -match "\.whl$" -and (Test-Path -LiteralPath $RequestedSpec -PathType Leaf)
    if ($CheckBaseline -and -not $ExplicitWheel -and -not $ExpectedVerBase) {
        throw "$PkgName 预检需要精确版本（例如 $PkgName==2.11.0）或现有本地 wheel 路径: $RequestedSpec"
    }
    $Candidates = if ($ExplicitWheel) {
        Get-Item -LiteralPath $RequestedSpec
    } else {
        Get-ChildItem -LiteralPath $WheelDir -Filter "*.whl" -File | Sort-Object Name
    }
    $MismatchReasons = @()

    foreach ($Whl in $Candidates) {
        $BaseNoExt = [System.IO.Path]::GetFileNameWithoutExtension($Whl.Name)
        $Parts = $BaseNoExt.Split("-")
        if ($Parts.Length -lt 5) {
            if ($ExplicitWheel) { $MismatchReasons += "$($Whl.Name): wheel 文件名缺少标签" }
            continue
        }
        $WhlPkg = $Parts[0].ToLowerInvariant().Replace("-", "_")
        if ($WhlPkg -ne $NormTargetPkg) {
            if ($ExplicitWheel) { $MismatchReasons += "$($Whl.Name): 包名不匹配 $PkgName" }
            continue
        }

        if ($Whl.Name -match "%2[Bb]") {
            $MismatchReasons += "$($Whl.Name): 文件名含 %2B，请将其重命名为 '+' 后重试"
            continue
        }

        $WhlVer = $Parts[1]
        $WhlPyTag = $Parts[$Parts.Length - 3].ToLowerInvariant()
        $WhlAbiTag = $Parts[$Parts.Length - 2].ToLowerInvariant()
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
            if ($WhlPyTag -ne $ExpectedPyTag -and ($CheckBaseline -or $WhlPyTag -ne "py3")) {
                $MismatchReasons += "$($Whl.Name): Python标签=$WhlPyTag（期望 $ExpectedPyTag）"
                continue
            }
            if ($WhlAbiTag -ne $ExpectedPyTag -and ($CheckBaseline -or $WhlAbiTag -notin @("abi3", "none"))) {
                $MismatchReasons += "$($Whl.Name): ABI标签=$WhlAbiTag（期望 $ExpectedPyTag）"
                continue
            }
            if ($WhlPlatTag -ne $ExpectedPlatTag -and ($CheckBaseline -or $WhlPlatTag -ne "any")) {
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

if ($CheckCudaWheels -and (-not $CudaWheelDir -or $SkipAI)) {
    throw "-CheckCudaWheels 需要指定 -CudaWheelDir，且不能与 -SkipAI 同用。"
}

$ExpectedPyTag = "cp312"
$CorePyMeta = $null
if (-not $CheckCudaWheels -and (-not $SkipCore -or -not $SkipAI)) {
    if (-not $PythonExe) {
        $Auto312 = Resolve-LauncherPython -SpecVersion "3.12"
        if (-not $Auto312 -and $AutoInstallPython) {
            $Auto312 = Install-PythonViaWinget -SpecVersion "3.12"
        }
        if ($Auto312) {
            $PythonExe = $Auto312
            Write-Host "自动检测到 Python 3.12 x64: $PythonExe" -ForegroundColor Gray
        } else {
            $FallbackCmd = Get-Command python -ErrorAction SilentlyContinue
            $FallbackDetail = ""
            if ($FallbackCmd) {
                if ($AllowUntestedPython) {
                    $PythonExe = $FallbackCmd.Source
                } else {
                    try {
                        $FbMeta = Test-PythonSpec -Exe $FallbackCmd.Source -ExpectedMajor 3 -ExpectedMinor 12
                        $FallbackDetail = "当前系统默认 python 为 $($FbMeta.Version) ($($FbMeta.Arch))。"
                    } catch {
                        $FallbackDetail = "当前默认 python 不可用或为 Microsoft Store 占位快捷方式。"
                    }
                }
            }
            if (-not $PythonExe) {
                throw ("未在本机找到 Python 3.12 x64。${FallbackDetail}AI Worker 实测要求 Python 3.12 x64 (cu128 + onnxruntime-gpu 1.26.0)。" +
                    "请先安装 Python 3.12 (64位): https://www.python.org/downloads/windows/ 或运行 `winget install -e --id Python.Python.3.12`；" +
                    "也可通过 `-PythonExe <Python3.12路径>`（例如 `-PythonExe C:\Python312\python.exe`）指定。")
            }
        }
    }

    $CorePyMeta = Test-PythonSpec -Exe $PythonExe -ExpectedMajor 3 -ExpectedMinor 12
    if (-not $CorePyMeta.Matches) {
        $msg = "检测到 Core/AI Python 为 $($CorePyMeta.Version) ($($CorePyMeta.Arch))；实测基线为 Python 3.12 x64 (cu128 + onnxruntime-gpu 1.26.0)。"
        if (-not $AllowUntestedPython) {
            throw "$msg 请安装 Python 3.12 (64位): https://www.python.org/downloads/windows/ 或使用 `-PythonExe C:\Python312\python.exe`（高阶用户可加 `-AllowUntestedPython`）。"
        }
        Write-Warning $msg
    }
    $ExpectedPyTag = "cp$($CorePyMeta.Major)$($CorePyMeta.Minor)"
}

$ExpectedCudaTag = "cu128"
if ($CudaIndexUrl -and ($CudaIndexUrl -match "(cu[0-9]+)$")) {
    $ExpectedCudaTag = $Matches[1].ToLowerInvariant()
}
$ExpectedPlatTag = "win_amd64"
$ResolvedCudaWheelDir = ""
$LocalWheels = @()
$MissingOnlineSpecs = @()
if (-not $SkipAI -and $CudaWheelDir) {
    if (-not (Test-Path -LiteralPath $CudaWheelDir -PathType Container)) {
        throw "指定的 -CudaWheelDir 目录不存在: $CudaWheelDir"
    }
    $ResolvedCudaWheelDir = (Resolve-Path -LiteralPath $CudaWheelDir).Path
    $PackageJobs = @(
        @{ Name = "torch"; Spec = $TorchSpec },
        @{ Name = "torchaudio"; Spec = $TorchaudioSpec },
        @{ Name = "torchvision"; Spec = $TorchvisionSpec }
    )
    foreach ($Item in $PackageJobs) {
        if (-not $Item.Spec) {
            if ($CheckCudaWheels) { throw "CUDA wheel 预检要求完整三件套，$($Item.Name) 的版本或路径为空。" }
            continue
        }
        $MatchedWhl = Resolve-LocalCudaWheel `
            -WheelDir $ResolvedCudaWheelDir `
            -PkgName $Item.Name `
            -RequestedSpec $Item.Spec `
            -ExpectedCudaTag $ExpectedCudaTag `
            -ExpectedPyTag $ExpectedPyTag `
            -ExpectedPlatTag $ExpectedPlatTag `
            -SkipAbiStrict:$AllowUntestedPython `
            -CheckBaseline:$CheckCudaWheels
        if ($MatchedWhl) {
            $LocalWheels += $MatchedWhl
        } else {
            $MissingOnlineSpecs += $Item.Spec
        }
    }
    if ($LocalWheels.Count -eq 0) {
        throw "在 -CudaWheelDir '$ResolvedCudaWheelDir' 中未找到匹配的本地 wheel。缺少: $($MissingOnlineSpecs -join ', ')。"
    }
}
if ($CheckCudaWheels) {
    if ($AllowUntestedPython) {
        Write-Warning "已按 -AllowUntestedPython 跳过 Python、ABI 与平台标签匹配。"
    }
    foreach ($WhlPath in $LocalWheels) {
        Write-Host "匹配: $([System.IO.Path]::GetFileName($WhlPath))"
    }
    if ($MissingOnlineSpecs.Count -gt 0) {
        throw "CUDA wheel 预检未通过。缺少本地 wheel: $($MissingOnlineSpecs -join ', ')。"
    }
    Write-Host "CUDA wheel 文件名预检通过。此步骤未检查文件内容或传递依赖。" -ForegroundColor Green
    return
}

if (-not $SkipCore) {
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
} else {
    Write-Host "=== [1/3] 已跳过 Core 桌面环境初始化 (-SkipCore) ===" -ForegroundColor Gray
}

if (-not $SkipAI) {
    $AiVenv = if ($AiVenvPath) { $AiVenvPath } else { Join-Path $RepoRoot ".venv-ai" }
    $AiPy = Join-Path $AiVenv "Scripts\python.exe"
    if (-not (Test-Path $AiPy)) {
        Invoke-Checked $PythonExe @("-m", "venv", $AiVenv)
    }
    Invoke-Checked $AiPy @("-m", "pip", "install", "--upgrade", "pip")

    if ($ResolvedCudaWheelDir) {
        Write-Host "=== [2/3] 初始化隔离 RTX 5060 Ti AI Worker 环境 ($AiVenv) [优先本地 wheel: $ResolvedCudaWheelDir] ===" -ForegroundColor Green
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
    $AiReportArgs = if ($SkipCore) {
        @("scripts\check_env.py", "--json", "--check-ai-packages", "--no-write")
    } else {
        @("scripts\check_env.py", "--json", "--check-ai-packages", "--write-report", "SYSTEM_REPORT.md")
    }
    Invoke-Checked $AiPy $AiReportArgs
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
        if (-not $MidiPythonExe -and $AutoInstallPython) {
            $MidiPythonExe = Install-PythonViaWinget -SpecVersion "3.11"
        }
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
        Write-Host "如需启用 Spotify Basic Pitch CPU MIDI 转录，请先安装 Python 3.11 x64 (winget install -e --id Python.Python.3.11) 后执行:" -ForegroundColor Yellow
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
