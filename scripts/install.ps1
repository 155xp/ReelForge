# ReelForge's one-line install for Windows. Paste this into PowerShell:
#   irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 | iex
# It downloads the newest ReelForge-<version>-Windows.zip from GitHub, checks it against the release's
# SHA256SUMS.txt, unpacks it into your user folder (%USERPROFILE%\ReelForge) and runs setup.bat there, ReelForge's
# first-run screens. Nothing goes through the browser, so there's no download warning and no "Windows protected your
# PC". It never touches a ReelForge folder that's already there (update that one from its Updates tab), except one the
# old Windows installer made: that one's Updates tab only knows how to run a newer installer, and ReelForge has none
# now, so this updates it in place instead, keeping everything of yours as an update does. Set these before the
# command to change what it does:
#   $env:REELFORGE_DIR = "D:\ReelForge"    install somewhere else
#   $env:REELFORGE_NO_SETUP = "1"          only download and unpack; double-click setup.bat yourself later
#   $env:REELFORGE_RELEASE = "<url>"       take the downloads from somewhere else (for testing)
# The release workflow attaches this file to every release. Windows PowerShell 5.1 runs it, so it stays plain
# ASCII and avoids anything newer.

& {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"     # Windows PowerShell downloads crawl while it draws a progress bar
    $release = if ($env:REELFORGE_RELEASE) { $env:REELFORGE_RELEASE.TrimEnd("/") } else { "https://github.com/dan2756/ReelForge/releases/latest/download" }

    function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

    if ($PSVersionTable.PSEdition -eq "Core" -and -not $IsWindows) {
        Say "This installs the Windows version. On macOS or Linux, paste this into Terminal instead:" "Yellow"
        Say "  curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | bash"
        return
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $dir = if ($env:REELFORGE_DIR) { $env:REELFORGE_DIR } else { Join-Path $env:USERPROFILE "ReelForge" }
    if (-not $env:REELFORGE_DIR) {
        # The old Windows installer let you pick another folder; its entry in Windows' list of apps says which
        $entry = Get-ItemProperty -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{39D29FF3-A243-4140-8CD2-E69CC877A496}_is1" -ErrorAction SilentlyContinue
        if ($entry -and $entry.InstallLocation -and (Test-Path -LiteralPath (Join-Path $entry.InstallLocation "unins000.exe"))) {
            $dir = $entry.InstallLocation
        }
    }
    $dir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($dir).TrimEnd("\")
    $python = Join-Path $dir ".venv\Scripts\python.exe"
    $old = (Test-Path -LiteralPath (Join-Path $dir "unins000.exe")) -and (Test-Path -LiteralPath (Join-Path $dir "studio\__init__.py"))
    if ($old) {
        if (-not (Test-Path -LiteralPath $python)) {
            Say "The ReelForge in $dir isn't set up yet. Double-click setup.bat in that folder, then paste the install command again." "Yellow"
            return
        }
        $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            try { $_.Path -and $_.Path.StartsWith($dir + "\", [StringComparison]::OrdinalIgnoreCase) } catch { $false } })
        if ($running.Count) {
            Say "ReelForge is open, or reading your stats. Close it, then paste the install command again." "Yellow"
            return
        }
        Say "The ReelForge in $dir came from the old Windows installer, so its Updates tab can't install new versions."
        Say "This updates it instead. Your channel, videos, stats, logins and settings stay as they are."
    } elseif ((Test-Path -LiteralPath $dir) -and (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1)) {
        Say "There's already a ReelForge folder at $dir, so nothing was changed." "Yellow"
        Say "To update it, open ReelForge and go to Updates (type reelforge 6). To put another copy somewhere else:"
        Say '  $env:REELFORGE_DIR = "D:\ReelForge"   then paste the install command again'
        return
    }

    $parent = Split-Path -Parent $dir
    $tag = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $work = Join-Path ([IO.Path]::GetTempPath()) "reelforge-install-$tag"
    $unpack = $null
    $pattern = '^([0-9a-fA-F]{64}) +\*?(ReelForge-[0-9A-Za-z.-]+-Windows\.zip)$'
    try {
        New-Item -ItemType Directory -Force -Path $work, $parent | Out-Null
        # Full folder names from here on: a short 8.3 name such as C:\Users\JOHNSM~1 can stop PowerShell deleting
        # what it unpacked, and stops Windows PowerShell unzipping at all
        $work = (Get-Item -LiteralPath $work -Force).FullName
        $dir = Join-Path (Get-Item -LiteralPath $parent -Force).FullName (Split-Path -Leaf $dir)
        $unpack = Join-Path (Split-Path -Parent $dir) ".reelforge-unpack-$tag"    # beside the target: the last step is a rename
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
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        if ($old) {
            Say "Unpacking it..."
            [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpack)
            $top = @(Get-ChildItem -LiteralPath $unpack -Force)
            if ($top.Count -ne 1 -or -not $top[0].PSIsContainer) { throw "$name isn't laid out the way ReelForge's are." }
            # The new version's own updater puts it in place, with the rules ReelForge's Updates tab follows
            Push-Location -LiteralPath $top[0].FullName
            try { & $python -B -m studio.update --into $dir } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { throw "the update stopped. ReelForge still works as it was; paste the install command to try again." }
        } else {
            Say "Unpacking it into $dir..."
            [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpack)
            $top = @(Get-ChildItem -LiteralPath $unpack -Force)
            if ($top.Count -ne 1 -or -not $top[0].PSIsContainer) { throw "$name isn't laid out the way ReelForge's are." }
            if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Force }     # the empty folder found above
            Move-Item -LiteralPath $top[0].FullName -Destination $dir
        }
    } catch {
        Say "ReelForge wasn't $(if ($old) { 'updated' } else { 'installed' }): $($_.Exception.Message)" "Red"
        return
    } finally {
        # Tidying up never stops the install: a folder that won't go is just left in Temp or beside ReelForge
        foreach ($leftover in $work, $unpack) {
            try { if ($leftover -and (Test-Path -LiteralPath $leftover)) { Remove-Item -LiteralPath $leftover -Recurse -Force } } catch { }
        }
    }

    if ($old) {
        Say "ReelForge in $dir is up to date. Open it as usual." "Green"
        return
    }
    Say "ReelForge is in $dir" "Green"
    if ($env:REELFORGE_NO_SETUP) {
        Say "Double-click setup.bat in that folder when you're ready to set it up."
        return
    }
    Say "Starting setup..."
    & (Join-Path $dir "setup.bat")
}
