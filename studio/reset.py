"""Starting over, and leaving: factory reset and uninstall (the Settings tab's danger zone, or the commands).

  reelforge reset [--yes]                     every channel's settings, log-ins and stats back to brand-new, then
                                              first-time setup again; your videos stay where they are
  reelforge uninstall [--yes] [--remove-videos]
                                              remove ReelForge from this computer; your videos and channels are kept
                                              in a folder beside it unless you say otherwise

Neither deletes anything for good:

  Factory reset moves what it clears into backups/factory-reset-<date>/ in the ReelForge folder (move it back to
  undo; delete it once you're sure). Blender, ffmpeg, the sounds and the window's packages stay, so nothing is
  downloaded again.

  Uninstall turns off the hourly stats read and the reelforge command, puts ReelForge's icon (and on Windows its
  Windows Terminal profile and the installer's Start menu folder) in the Recycle Bin or the Trash, moves your videos
  and channel answers to "ReelForge videos and channels" beside the ReelForge folder, then puts the ReelForge folder
  in the Recycle Bin or the Trash: the app, Blender, ffmpeg, Bun, its Python, your stats, log-ins and settings.

ReelForge has its own files open while it runs (the stats database, the browser log-ins, its Python), so the window
only asks for either (PENDING) and quits with exit code 75; the launcher, starting ReelForge again, does it before
anything opens them. On Windows the last step, the folder itself, runs in a small PowerShell window of its own once
ReelForge has closed: a running program's folder can't be moved there. It renames the folder into the Recycle Bin and
writes the bin's record of it ($I) itself, because Windows' own delete calls quietly delete a folder too big for the
bin for good. A test copy (TEST-COPY.txt) or STUDIO_DRY_SYSTEM=1 leaves the computer's settings alone; a git copy of
ReelForge (one you work on) can't be uninstalled from inside.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import KIT_NAME, profiles
from . import paths as P

ROOT = P.ROOT
PENDING = ROOT / ".reelforge-pending.json"   # {"do": "reset"} or {"do": "uninstall", "keep": true}
BACKUPS = ROOT / "backups"
KEEP_NAME = f"{KIT_NAME} videos and channels"
BIN = "Recycle Bin" if P.WINDOWS else "Trash"
BOOTSTRAP_MARK = "reelforge-bootstrap"       # the same as studio.generate.BOOTSTRAP_MARK: first-time setup's to replace
INNO_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{39D29FF3-A243-4140-8CD2-E69CC877A496}_is1"
EMPTY = {".gitkeep", "README.md"}            # what a fresh download's episodes/, completed videos/ and research/ hold


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _inside(path: Path, folder: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (OSError, ValueError):
        return False


def _has_files(folder: Path) -> bool:
    """A folder with something of yours in it (not just the download's placeholders)."""
    try:
        return folder.is_dir() and any(f.name not in EMPTY for f in folder.iterdir())
    except OSError:
        return False


def _size(path: Path) -> tuple[int, int]:
    """(files, bytes) under a file or folder."""
    if path.is_file():
        return 1, path.stat().st_size
    n = total = 0
    for dirpath, _, names in os.walk(path):
        for name in names:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
                n += 1
            except OSError:
                pass
    return n, total


def fmt_size(n: int) -> str:
    for unit, step in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= step:
            return f"{n / step:.1f} {unit}"
    return f"{n} bytes"


def _move(src: Path, dst: Path, wait: float = 10) -> str | None:
    """Rename src to dst (the same drive, so nothing is copied), trying again for a few seconds while something has
    it open. Returns what went wrong, or None."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    end = time.monotonic() + wait
    while True:
        try:
            os.rename(src, dst)
            return None
        except OSError as e:
            if time.monotonic() >= end:
                return e.strerror or str(e)
            time.sleep(0.5)


def _free(folder: Path, name: str) -> Path:
    """folder/name, or folder/name 2, 3 ... so nothing already there is replaced."""
    n, candidate = 1, folder / name
    while candidate.exists():
        n += 1
        candidate = folder / f"{name} {n}"
    return candidate


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def git_copy() -> bool:
    """A git copy of ReelForge (one being worked on): uninstall refuses, so nobody loses their work."""
    return (ROOT / ".git").exists()


def confirm_word(profile: profiles.Profile | None = None) -> str:
    """What you type to confirm: the channel's name (the one on the profile button)."""
    return (profile or profiles.current()).name


def matches(typed: str, profile: profiles.Profile | None = None) -> bool:
    return " ".join(str(typed or "").split()).casefold() == " ".join(confirm_word(profile).split()).casefold()


# ---------------------------------------------------------------- factory reset

def reset_items() -> list[tuple[Path, str]]:
    """What factory reset moves into its backup, with what each one is (only what's there)."""
    main = profiles.main()
    items = [
        (main.my_studio, "your channel's answers, settings and channel bible"),
        (main.config, "ReelForge's settings and your connected accounts"),
        (main.data, "your stats, notifications and log-ins"),
        (ROOT / ".claude" / "settings.local.json", "Claude Code's settings for this folder"),
        (profiles.FOLDER, "your other channels' profiles, with their videos"),
    ]
    for name in ("CLAUDE.md", "AGENTS.md"):
        f = ROOT / name
        try:
            ours = BOOTSTRAP_MARK in f.read_text(encoding="utf-8", errors="replace")[:600]
        except OSError:
            continue
        if not ours:
            items.append((f, "your AI's notes on the channel"))
    research = ROOT / "research"
    if research.is_dir():
        items += [(f, "your AI's research") for f in sorted(research.iterdir()) if f.name not in EMPTY]
    return [(p, what) for p, what in items if p.exists()]


def bootstrap_note(when: str, backup: str) -> str:
    """CLAUDE.md / AGENTS.md until first-time setup runs again (it replaces them)."""
    return (f"<!-- {BOOTSTRAP_MARK}: first-time setup replaces this file with one written for your channel. -->\n"
            f"# {KIT_NAME} (reset, not set up yet)\n\n"
            f"This folder is **{KIT_NAME}**, a kit for making faceless short-form videos: Blender builds and renders "
            "each scene, Python draws the text and mixes the sound, ffmpeg encodes, an automatic QA gate checks every "
            f"video, and the {KIT_NAME} window (type `reelforge` in a terminal) is where the person you're working "
            "with sees their stats and posts from, by hand.\n\n"
            f"It was reset to brand-new on {when}, and first-time setup hasn't run again yet. Ask them to open "
            f"{KIT_NAME} (type `reelforge`) and answer first-time setup's questions. Or run the interview here in "
            "chat: `reelforge channel --questions` lists the questions as JSON; write their answers to a file and "
            "run `reelforge channel --answers FILE.json`, which writes this file for their channel.\n\n"
            f"Their old settings, notes and stats are in `{backup}` (move them back to undo the reset).\n")


@dataclass
class Done:
    """What a factory reset or an uninstall did, for the window's notice or the terminal."""
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    where: Path | None = None   # the backup (reset) or the kept videos (uninstall)


def factory_reset(say=print) -> Done:
    """Move every channel's settings, log-ins and stats into backups/factory-reset-<date>/ and turn off the hourly
    stats read (first-time setup turns it on again). Your videos stay."""
    done = Done()
    items = reset_items()
    dest = BACKUPS / f"factory-reset-{_stamp()}"
    done.where = dest
    for path, what in items:
        rel = path.relative_to(ROOT)
        say(f"  {rel}: {what}")
        err = _move(path, dest / rel)
        if err:
            done.problems.append(f"{rel} ({err})")
    if any(p.name in ("CLAUDE.md", "AGENTS.md") for p, _ in items):
        note = bootstrap_note(datetime.now().strftime("%d %B %Y"), f"backups/{dest.name}")
        for name in ("CLAUDE.md", "AGENTS.md"):
            if not (ROOT / name).exists():
                (ROOT / name).write_text(note, encoding="utf-8", newline="\n")
    if dest.is_dir():
        (dest / "README.txt").write_text(
            f"{KIT_NAME}'s factory reset moved these here on {datetime.now():%d %B %Y at %H:%M}:\n\n"
            + "".join(f"  {p.relative_to(ROOT)}  ({what})\n" for p, what in items)
            + f"\nTo undo it, close {KIT_NAME} and move them back into the {KIT_NAME} folder, to the same places.\n"
              "The log-ins in dashboard/data/browser are your own: delete this folder once you're sure you don't "
              "need it.\n", encoding="utf-8")
    try:
        from . import stats_schedule

        if stats_schedule.status() == "on":
            say("  " + stats_schedule.disable())
    except Exception as e:  # the scheduler isn't there: nothing to turn off
        done.lines.append(f"The hourly stats read couldn't be checked ({e}).")
    done.lines.append(f"Everything it cleared is in {P.rel(dest)}." if items else "There was nothing to clear.")
    return done


# ---------------------------------------------------------------- uninstall: what goes, and what's kept

def _config(p: profiles.Profile) -> dict:
    try:
        with p.config.open("rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def video_folders(p: profiles.Profile) -> list[Path]:
    """Where a channel's videos are: its episodes and completed videos, and the Publish tab's other video folder
    (dashboard/config.toml's paths, which start from the profile's dashboard folder)."""
    cfg = _config(p)
    out: list[Path] = []
    for key, default in (("episodes_dir", "../episodes"), ("completed_dir", "../completed videos"),
                         ("videos_dir", "videos")):
        raw = Path(str(cfg.get(key) or default)).expanduser()
        path = raw if raw.is_absolute() else p.dashboard / raw
        try:
            path = path.resolve()
        except OSError:
            continue
        if not any(_same(path, q) for q in out):
            out.append(path)
    return out


def _folder_name(name: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return clean or "channel"


@dataclass
class Keep:
    """One channel's videos and answers, and where uninstall puts them."""
    profile: profiles.Profile
    folders: list[Path]       # inside the ReelForge folder, with something in them: these move
    outside: list[Path]       # outside it: left where they are
    files: int = 0
    bytes: int = 0


def keep_plan() -> list[Keep]:
    out = []
    for p in profiles.every():
        inside, outside = [], []
        for f in video_folders(p):
            if _inside(f, ROOT):
                if _has_files(f):
                    inside.append(f)
            elif f.is_dir():
                outside.append(f)
        if _has_files(p.my_studio):
            inside.append(p.my_studio)
        k = Keep(p, inside, outside)
        for f in inside:
            n, b = _size(f)
            k.files += n
            k.bytes += b
        if inside or outside:
            out.append(k)
    return out


def keep_folder() -> Path:
    return _free(ROOT.parent, KEEP_NAME)


def system_items() -> list[str]:
    """The parts of ReelForge outside its folder that uninstall turns off or bins."""
    out = ["the hourly stats read", "the reelforge command"]
    if P.WINDOWS:
        out += ["the desktop icon", "ReelForge's Windows Terminal profile"]
    else:
        out.append("ReelForge in Applications" if P.MAC else "ReelForge in your app menu")
    return out


def uninstall_info() -> dict:
    """What the Uninstall dialog (and reelforge uninstall) says before anything happens."""
    plan = keep_plan()
    return {
        "root": str(ROOT), "bin": BIN, "keep_to": str(keep_folder()), "git": git_copy(),
        "test": P.test_copy(), "system": system_items(),
        "videos": sum(k.files for k in plan), "videos_size": fmt_size(sum(k.bytes for k in plan)),
        "outside": [str(f) for k in plan for f in k.outside],
        "channels": [{"name": k.profile.name, "folders": [P.rel(f) for f in k.folders]} for k in plan if k.folders],
        "word": confirm_word(),
    }


def keep_videos(say=print) -> Done:
    """Move each channel's videos and answers (inside the ReelForge folder) to "ReelForge videos and channels"
    beside it, a folder for each channel."""
    done = Done()
    plan = [k for k in keep_plan() if k.folders]
    if not plan:
        done.lines.append("There were no videos or channel answers in the ReelForge folder to keep.")
        return done
    dest = keep_folder()
    done.where = dest
    for k in plan:
        channel = dest / _folder_name(k.profile.name)
        for f in k.folders:
            target = _free(channel, f.name)
            say(f"  {k.profile.name}: {P.rel(f)} -> {target}")
            err = _move(f, target)
            if err:
                done.problems.append(f"{P.rel(f)} ({err})")
    if not dest.is_dir():   # nothing could be moved
        return done
    (dest / "README.txt").write_text(
        f"Kept when {KIT_NAME} was uninstalled on {datetime.now():%d %B %Y at %H:%M}: each channel's videos (episodes, "
        f"completed videos) and its answers from first-time setup (my-studio). {KIT_NAME} itself went to the {BIN}.\n"
        f"Install {KIT_NAME} again and move these back into its folder to carry on where you left off.\n",
        encoding="utf-8")
    done.lines.append(f"Your videos and channels are in {dest}.")
    return done


def _recycle_small(path: Path) -> bool:
    """A shortcut or a small folder of ReelForge's to the Recycle Bin / Trash (small, so it always fits there)."""
    try:
        from dashboard import desktop
    except ImportError:
        return False
    return desktop.recycle(path) and not path.exists()


def system_off(say=print) -> list[str]:
    """Turn off everything ReelForge set up outside its folder. Returns what couldn't be done."""
    problems: list[str] = []
    if P.dry_system():
        say("  A test copy leaves the computer's settings alone (the command, the hourly job, the icon)."
            if P.test_copy() else "  (dry run) would turn off the hourly job and the command, and bin the icon")
        return problems
    from . import command, shortcut, stats_schedule

    try:
        if stats_schedule.status() == "on":
            say("  " + stats_schedule.disable())
    except Exception as e:
        problems.append(f"the hourly stats read ({e}): turn it off with your system's task scheduler")
    try:
        if command.status() == "on":
            say("  " + command.disable())
    except Exception as e:
        problems.append(f"the reelforge command ({e})")
    try:
        if shortcut.ours():
            icon = shortcut.path()
            if _recycle_small(icon):
                say(f"  ReelForge's icon is in the {BIN}.")
            else:
                problems.append(f"the icon at {icon}")
    except Exception as e:
        problems.append(f"the icon ({e})")
    if P.WINDOWS:
        problems += _windows_extras(say)
    return problems


def _windows_extras(say) -> list[str]:
    """Windows Terminal's ReelForge profile, and what the Windows installer added: its Start menu folder and its
    entry in Settings > Apps (only when they're this folder's)."""
    problems: list[str] = []
    from . import terminal_profile

    frag = terminal_profile.folder()
    try:
        names_us = frag.is_dir() and str(ROOT) in (frag / f"{KIT_NAME}.json").read_text(encoding="utf-8")
    except OSError:
        names_us = False
    if names_us:
        if _recycle_small(frag):
            say(f"  Windows Terminal's ReelForge profile is in the {BIN}.")
        else:
            problems.append(f"Windows Terminal's ReelForge profile ({frag})")
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INNO_KEY) as k:
            where = str(winreg.QueryValueEx(k, "InstallLocation")[0])
    except OSError:
        return problems
    if not _same(Path(where), ROOT):
        return problems
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / KIT_NAME
    if start.is_dir() and not _recycle_small(start):
        problems.append(f"the Start menu folder {start}")
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, INNO_KEY)
        say("  ReelForge is off the list in Settings > Apps.")
    except OSError as e:
        problems.append(f"its entry in Settings > Apps ({e})")
    return problems


# ---------------------------------------------------------------- uninstall: the folder itself

WINDOWS_BIN = r"""
param([string]$Root, [string]$Kept, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Uninstalling ReelForge'
function Done($code) {
  Write-Host ''
  if (-not $NoPause) { Read-Host 'Press Enter to close this window' | Out-Null }
  exit $code
}
Write-Host "Uninstalling ReelForge: $Root"
Write-Host ''
Write-Host 'Waiting for ReelForge to close (close any window or terminal still open in its folder)...'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$bin = Join-Path ([IO.Path]::GetPathRoot($Root)) ('$Recycle.Bin\' + $sid)
if (-not [IO.Directory]::Exists($bin)) {
  # The bin's folder for this drive appears with its first file: a tiny one of our own, sent there the usual way.
  $probe = Join-Path (Split-Path $Root) ('reelforge-bin-' + [guid]::NewGuid().ToString('N') + '.txt')
  try {
    [IO.File]::WriteAllText($probe, 'ReelForge checked the Recycle Bin on this drive. You can delete this.')
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($probe, 'OnlyErrorDialogs', 'SendToRecycleBin')
  } catch {}
}
$chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
$name = Split-Path $Root -Leaf
$ext = if ($name.Contains('.')) { $name.Substring($name.LastIndexOf('.')) } else { '' }
$id = -join (1..6 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
$useBin = [IO.Directory]::Exists($bin)
$target = if ($useBin) { Join-Path $bin ('$R' + $id + $ext) } else { "$Root (uninstalled)" }
$moved = $false
for ($i = 0; $i -lt 600 -and -not $moved; $i++) {
  try { [IO.Directory]::Move($Root, $target); $moved = $true } catch { Start-Sleep -Milliseconds 1000 }
}
if (-not $moved) {
  Write-Host ''
  Write-Host "ReelForge's folder is still in use, so it was left where it is: $Root"
  Write-Host 'Close everything open in it and delete it yourself (or run reelforge uninstall again).'
  Done 1
}
if (-not $useBin) {
  Write-Host ''
  Write-Host "This drive has no Recycle Bin, so ReelForge's folder was renamed instead: $target"
  Write-Host 'Delete it yourself once you are sure.'
  if ($Kept) { Write-Host "Your videos and channels: $Kept" }
  Done 0
}
$bytes = [int64]0
Get-ChildItem -LiteralPath $target -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object { $bytes += $_.Length }
# The bin's record of it ($I): version 2, size, when (UTC FILETIME), the length of its old path with the end NUL,
# and that path in UTF-16.
$ms = New-Object IO.MemoryStream
$w = New-Object IO.BinaryWriter($ms)
$w.Write([int64]2); $w.Write([int64]$bytes); $w.Write([DateTime]::UtcNow.ToFileTimeUtc())
$w.Write([int32]($Root.Length + 1)); $w.Write([Text.Encoding]::Unicode.GetBytes($Root + [char]0)); $w.Flush()
[IO.File]::WriteAllBytes((Join-Path $bin ('$I' + $id + $ext)), $ms.ToArray())
Start-Sleep -Milliseconds 500
$listed = @((New-Object -ComObject Shell.Application).Namespace(10).Items()) | Where-Object { $_.Path -eq $target }
Write-Host ''
if ($listed) {
  Write-Host 'ReelForge is in the Recycle Bin. Restore it from there if you change your mind,'
  $size = if ($bytes -ge 1e9) { '{0:N1} GB' -f ($bytes / 1e9) } else { '{0:N0} MB' -f [math]::Ceiling($bytes / 1e6) }
  Write-Host "or empty the bin to get the space back ($size)."
} else {
  Write-Host "ReelForge's folder was moved to $target, but the Recycle Bin doesn't list it yet."
  Write-Host 'Open the Recycle Bin to check; nothing was deleted.'
}
if ($Kept) { Write-Host ''; Write-Host "Your videos and channels: $Kept" }
Done 0
"""


def bin_folder(kept: Path | None, say=print) -> str | None:
    """Put the ReelForge folder in the Recycle Bin / Trash. On Windows a PowerShell window does it once ReelForge has
    closed (returns None: it reports there); elsewhere it's done here and now (a folder in use can still be moved).
    Returns what went wrong, or None."""
    kept_s = str(kept) if kept else ""
    if P.WINDOWS:
        script = Path(tempfile.gettempdir()) / f"reelforge-uninstall-{_stamp()}.ps1"
        script.write_text(WINDOWS_BIN, encoding="utf-8-sig")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                          "-Root", str(ROOT), "-Kept", kept_s], cwd=tempfile.gettempdir(), creationflags=flags,
                         stdin=subprocess.DEVNULL, close_fds=True)
        say(f"A small window finishes the job once {KIT_NAME} has closed: it puts the {KIT_NAME} folder in the "
            f"Recycle Bin and says when it's done.")
        return None
    try:
        from dashboard import desktop
    except ImportError:
        return "ReelForge's own helpers are missing"
    os.chdir(tempfile.gettempdir())   # not inside the folder being moved
    if not desktop.recycle(ROOT) or ROOT.exists():
        return f"couldn't move {ROOT} to the {BIN}"
    say(f"{KIT_NAME} is in the {BIN}. Put it back from there if you change your mind.")
    return None


def uninstall(keep: bool = True, say=print) -> Done:
    """Everything uninstall does, in order: the computer's settings, the videos you're keeping, then the folder."""
    done = Done()
    say(f"Turning off {', '.join(system_items())}...")
    done.problems += system_off(say)
    if keep:
        say("Keeping your videos and channels...")
        kept = keep_videos(say)
        done.problems += kept.problems
        done.lines += kept.lines
        done.where = kept.where
        if kept.problems:   # never bin a video that couldn't be moved out
            done.problems.append(f"{KIT_NAME}'s folder was left where it is, because some videos couldn't be moved "
                                 "out of it")
            return done
    PENDING.unlink(missing_ok=True)
    err = bin_folder(done.where, say)
    if err:
        done.problems.append(err)
    return done


# ---------------------------------------------------------------- asked for by the window

def request(what: str, keep: bool = True) -> None:
    """The window asks for a factory reset or an uninstall; the launcher does it when it starts ReelForge again."""
    data = {"do": what, "keep": bool(keep), "asked": datetime.now().isoformat(timespec="seconds")}
    PENDING.write_text(json.dumps(data) + "\n", encoding="utf-8")


def pending() -> dict | None:
    try:
        data = json.loads(PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("do") in ("reset", "uninstall") else None


def _report(done: Done, title: str) -> None:
    for line in done.lines:
        print(line)
    if done.problems:
        print(f"\n{title} didn't finish. These couldn't be moved:")
        for p in done.problems:
            print(f"  {p}")
        print(f"Close every other {KIT_NAME} window (and wait for a stats read to finish), then try again.")


def finish_pending() -> int | None:
    """What the launcher does first: a factory reset or an uninstall the window asked for. None: carry on opening
    ReelForge (after a reset: first-time setup), else the exit code to stop with."""
    job = pending()
    if job is None:
        return None
    if job["do"] == "reset":
        print(f"Factory reset: putting {KIT_NAME} back to brand-new. Moving into a backup:")
        done = factory_reset()
        _report(done, "The factory reset")
        if done.problems:
            return 1                # PENDING stays: the next start tries again
        PENDING.unlink(missing_ok=True)
        print("\nStarting first-time setup...\n")
        return None
    print(f"Uninstalling {KIT_NAME} ({ROOT}).")
    done = uninstall(bool(job.get("keep", True)))
    _report(done, "Uninstalling")
    PENDING.unlink(missing_ok=True)
    return 1 if done.problems else 0


# ---------------------------------------------------------------- the commands

def _ask(word: str) -> bool:
    try:
        typed = input(f'Type "{word}" to confirm (anything else stops): ')
    except EOFError:
        return False
    return matches(typed)


def reset_main(argv: list[str]) -> int:
    yes = "--yes" in argv or "-y" in argv
    items = reset_items()
    print(f"Factory reset puts {KIT_NAME} back to brand-new: every channel's settings, log-ins and stats, then "
          "first-time setup again.")
    print("It moves these into a backup in backups/ (nothing is deleted):")
    for p, what in items:
        print(f"  {P.rel(p)}: {what}")
    if not items:
        print("  (nothing: it's brand-new already)")
    print("Your videos (episodes, completed videos) stay where they are. Close every other ReelForge window first.\n")
    if not yes:
        if not sys.stdin.isatty():
            print("Run it in a terminal to confirm, or add --yes.")
            return 2
        if not _ask(confirm_word()):
            print("Nothing was changed.")
            return 1
    done = factory_reset(say=lambda line: None)   # the list above says what moves
    _report(done, "The factory reset")
    if done.problems:
        return 1
    if sys.stdin.isatty() and sys.stdout.isatty():
        from .__main__ import first_run

        return first_run("onboard")
    print("Run reelforge to answer first-time setup's questions again.")
    return 0


def uninstall_main(argv: list[str]) -> int:
    yes = "--yes" in argv or "-y" in argv
    keep = "--remove-videos" not in argv
    info = uninstall_info()
    if info["git"]:
        print(f"This {KIT_NAME} is a git copy ({ROOT}), so it isn't uninstalled from inside: delete the folder "
              "yourself when you're done with it.")
        return 2
    print(f"Uninstalling removes {KIT_NAME} from this computer:")
    print(f"  {ROOT} goes to the {BIN}: the app, Blender, ffmpeg, Bun, its Python, your stats, log-ins and settings")
    things = ", ".join(info["system"][:-1]) + " and " + info["system"][-1]
    print(f"  {things[:1].upper() + things[1:]} are turned off" + (" (not in a test copy)" if info["test"] else ""))
    if info["channels"]:
        if keep:
            print(f"Your videos and channels ({info['videos']} files, {info['videos_size']}) are kept first, in")
            print(f"  {info['keep_to']}")
        else:
            print(f"Your videos and channels ({info['videos']} files, {info['videos_size']}) go to the {BIN} with it "
                  "(--remove-videos).")
    for f in info["outside"]:
        print(f"Videos outside the ReelForge folder stay where they are: {f}")
    print()
    if not yes:
        if not sys.stdin.isatty():
            print("Run it in a terminal to confirm, or add --yes.")
            return 2
        if not _ask(info["word"]):
            print("Nothing was changed.")
            return 1
    done = uninstall(keep)
    _report(done, "Uninstalling")
    return 1 if done.problems else 0
