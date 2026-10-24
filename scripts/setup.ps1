# ReelForge setup for Windows. Double-click setup.bat (it runs this script).
#   setup.bat            set up everything (one list of what's missing, one yes), then onboarding
#   setup.bat -Yes       the same without questions (for an AI setting up for you, with your OK)
# Everything goes inside this folder (.venv, tools\); nothing is installed system-wide except Python itself, and
# only if you agree. Once Python is found, studio\bootstrap.py draws the first-run box and does the rest.
param([switch]$Yes, [switch]$NoOnboard)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"
$Title = if (Test-Path -LiteralPath (Join-Path $Root "TEST-COPY.txt")) { "ReelForge TEST setup" } else { "ReelForge setup" }
try { $Host.UI.RawUI.WindowTitle = $Title } catch { }

# The old Windows console opens small; make room for the first-run box if the screen allows (Windows Terminal
# keeps its own size and ignores this).
try {
    $raw = $Host.UI.RawUI
    $max = $raw.MaxPhysicalWindowSize
    $w = [Math]::Min(124, $max.Width); $h = [Math]::Min(40, $max.Height)
    if ($raw.WindowSize.Width -lt $w -or $raw.WindowSize.Height -lt $h) {
        $buf = $raw.BufferSize
        if ($buf.Width -lt $w -or $buf.Height -lt $h) {
            $raw.BufferSize = New-Object Management.Automation.Host.Size ([Math]::Max($buf.Width, $w)), ([Math]::Max($buf.Height, $h))
        }
        $raw.WindowSize = New-Object Management.Automation.Host.Size $w, $h
    }
} catch { }

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

function Ask($question, $default = $true) {
    if ($Yes) { Say "$question yes"; return $true }
    $hint = if ($default) { "[Y/n]" } else { "[y/N]" }
    while ($true) {
        $a = (Read-Host "$question $hint").Trim().ToLower()
        if ($a -eq "") { return $default }
        if ($a -in @("y", "yes")) { return $true }
        if ($a -in @("n", "no")) { return $false }
    }
}

function Test-Python($exe, $extra) {
    try {
        $out = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $ver, $path = $out[0].Trim(), $out[1].Trim()
        $major, $minor = $ver.Split(".") | ForEach-Object { [int]$_ }
        if ($major -eq 3 -and $minor -ge 11) { return $path }
    } catch { }
    return $null
}

function Find-Python {
    foreach ($v in "3.13", "3.12", "3.11", "3.14") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $p = Test-Python "py" @("-$v")
            if ($p) { return $p }
        }
    }
    foreach ($name in "python", "python3") {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike "*\WindowsApps\*") {     # skip the Microsoft Store's "python" stub
            $p = Test-Python $cmd.Source @()
            if ($p) { return $p }
        }
    }
    foreach ($guess in @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                         "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                         "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe")) {
        if (Test-Path -LiteralPath $guess) {
            $p = Test-Python $guess @()
            if ($p) { return $p }
        }
    }
    return $null
}

function Box($lines) {
    $width = ($lines | Measure-Object -Property Length -Maximum).Maximum + 4
    Say ("  +" + ("-" * $width) + "+") "Red"
    foreach ($l in $lines) { Write-Host "  | " -ForegroundColor Red -NoNewline; Write-Host $l.PadRight($width - 2) -NoNewline; Write-Host " |" -ForegroundColor Red }
    Say ("  +" + ("-" * $width) + "+") "Red"
}

$python = Find-Python
if (-not $python) {
    Clear-Host
    Say ""
    Write-Host "  reel" -ForegroundColor White -NoNewline; Write-Host "forge" -ForegroundColor Red -NoNewline; Say "  setup"
    Say ""
    Box @("ReelForge runs on Python 3.11 or newer, which isn't on this computer yet.",
          "It can install Python 3.13 for you now (from Microsoft's winget, for your user only).")
    Say ""
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask "Install Python 3.13 now?")) {
        winget install --exact --id Python.Python.3.13 --scope user --accept-package-agreements --source winget
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $python = Find-Python
    }
    if (-not $python) {
        Say ""
        Say "Install Python from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup.bat again." "Yellow"
        exit 1
    }
}

$bootArgs = @("-m", "studio.bootstrap")
if ($Yes) { $bootArgs += "--yes" }
if ($NoOnboard) { $bootArgs += "--no-onboard" }
& $python @bootArgs
exit $LASTEXITCODE
