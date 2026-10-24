# ReelForge's one-line install for Windows. Paste this into PowerShell:
#   irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 | iex
# It downloads the newest ReelForge-<version>-Windows.zip from GitHub, checks it against the release's
# SHA256SUMS.txt, unpacks it into your user folder (%USERPROFILE%\ReelForge) and runs setup.bat there, the same
# first-run screens the installer starts. Nothing goes through the browser, so there's no download warning and no
# "Windows protected your PC". It never touches a ReelForge folder that's already there: update that one from its
# Updates tab. Set these before the command to change what it does:
#   $env:REELFORGE_DIR = "D:\ReelForge"    install somewhere else
#   $env:REELFORGE_NO_SETUP = "1"          only download and unpack; double-click setup.bat yourself later
# The release workflow attaches this file to every release. Windows PowerShell 5.1 runs it, so it stays plain
# ASCII and avoids anything newer.

& {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"     # Windows PowerShell downloads crawl while it draws a progress bar
    $release = "https://github.com/dan2756/ReelForge/releases/latest/download"

    function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

    if ($PSVersionTable.PSEdition -eq "Core" -and -not $IsWindows) {
        Say "This installs the Windows version. For macOS or Linux, see https://github.com/dan2756/ReelForge/releases" "Yellow"
        return
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $dir = if ($env:REELFORGE_DIR) { $env:REELFORGE_DIR } else { Join-Path $env:USERPROFILE "ReelForge" }
    $dir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($dir)
    if ((Test-Path -LiteralPath $dir) -and (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1)) {
        Say "There's already a ReelForge folder at $dir, so nothing was changed." "Yellow"
        Say "To update it, open ReelForge and go to Updates (type reelforge 6). To put another copy somewhere else:"
        Say '  $env:REELFORGE_DIR = "D:\ReelForge"   then paste the install command again'
        return
    }

    $parent = Split-Path -Parent $dir
    $tag = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $work = Join-Path ([IO.Path]::GetTempPath()) "reelforge-install-$tag"
    $unpack = Join-Path $parent ".reelforge-unpack-$tag"      # beside the target, so the last step is a rename
    $pattern = '^([0-9a-fA-F]{64}) +\*?(ReelForge-[0-9A-Za-z.-]+-Windows\.zip)$'
    try {
        New-Item -ItemType Directory -Force -Path $work, $parent | Out-Null
        Say "Finding the newest ReelForge..."
        $sums = Join-Path $work "SHA256SUMS.txt"
        Invoke-WebRequest "$release/SHA256SUMS.txt" -OutFile $sums -UseBasicParsing
        $line = Get-Content -LiteralPath $sums | Where-Object { $_ -match $pattern } | Select-Object -First 1
        if (-not ($line -match $pattern)) { throw "the newest release lists no Windows download in SHA256SUMS.txt." }
        $want, $name = $Matches[1].ToLower(), $Matches[2]
        Say "Downloading $name..."
        $zip = Join-Path $work $name
        Invoke-WebRequest "$release/$name" -OutFile $zip -UseBasicParsing
        if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() -ne $want) {
            throw "$name doesn't match its checksum in SHA256SUMS.txt (the download broke or was changed)."
        }
        Say "Unpacking it into $dir..."
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpack)
        $top = @(Get-ChildItem -LiteralPath $unpack -Force)
        if ($top.Count -ne 1 -or -not $top[0].PSIsContainer) { throw "$name isn't laid out the way ReelForge's are." }
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Force }     # the empty folder found above
        Move-Item -LiteralPath $top[0].FullName -Destination $dir
    } catch {
        Say "ReelForge wasn't installed: $($_.Exception.Message)" "Red"
        return
    } finally {
        Remove-Item -LiteralPath $work, $unpack -Recurse -Force -ErrorAction SilentlyContinue
    }

    Say "ReelForge is in $dir" "Green"
    if ($env:REELFORGE_NO_SETUP) {
        Say "Double-click setup.bat in that folder when you're ready to set it up."
        return
    }
    Say "Starting setup..."
    & (Join-Path $dir "setup.bat")
}
