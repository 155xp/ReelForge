"""Moving ReelForge into a folder of its own: Move... on the Settings tab, or the command.

  reelforge move [FOLDER] [--yes]     move this ReelForge folder (to its own folder, home(), unless you name another)

ReelForge belongs in a folder of its own, the one the install line puts it in: C:\\Users\\<you>\\ReelForge on
Windows, ~/ReelForge on a Mac or Linux (home()). A copy kept somewhere else (on the Desktop, in Documents, inside a
folder that syncs) moves there in one step on the same drive, so nothing is copied and nothing is deleted:

  1. The folders the Publish tab reads outside the ReelForge folder (every profile's dashboard/config.toml:
     videos_dir, episodes_dir and completed_dir, which start from the profile's dashboard folder) are written down in
     full first, so they still name the same folders afterwards.
  2. The folder is renamed. A running program's folder can't be renamed on Windows, so there a small window does it
     once ReelForge has closed, waiting while anything still has a file in it open; elsewhere it's done at once, and
     the .venv's links to a Python inside the folder (setup's private one in tools/python) follow it.
  3. What named the old place follows it (`reelforge move --finish`, run from the new place): the reelforge command,
     ReelForge's icon, Windows Terminal's ReelForge profile and the hourly stats read, each only if it was this
     folder's. The window that opens next says where ReelForge is now.

It doesn't move a test copy (TEST-COPY.txt: it never changes the computer), a git copy (one being worked on), a copy
the old Windows installer made (Windows' list of apps knows it by its folder), one on another drive (that would mean
copying everything: copy it yourself, then run setup in the copy), or into a folder with something in it. Your AI's
chats about the old folder stay under that folder's name in Claude Code and Codex: open the new one from now on.

Standard library only.
"""

from __future__ import annotations

import json
import os
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
STATE = ".reelforge-moving.json"   # in the folder while it moves: where to, and what to point at the new place
MARKER = Path("dashboard") / "data" / "moved.json"   # once it has moved: the next window says so, once
KEYS = ("videos_dir", "episodes_dir", "completed_dir")   # dashboard/config.toml's folders (see dashboard/config.py)
STALE = 86400   # seconds after which the note of a move that never happened is tidied away


def home() -> Path:
    """Where ReelForge belongs: the folder the install line puts it in."""
    if P.WINDOWS:
        return Path(os.environ.get("USERPROFILE") or str(Path.home())) / KIT_NAME
    return Path.home() / KIT_NAME


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _inside(path: Path, folder: Path) -> bool:
    """path is folder, or somewhere in it (compared as written: neither has to be there)."""
    a = os.path.normcase(os.path.normpath(os.path.abspath(str(path))))
    b = os.path.normcase(os.path.normpath(os.path.abspath(str(folder))))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def at_home(root: Path | None = None) -> bool:
    """ReelForge is in its own folder already."""
    return _same(root or ROOT, home())


def _drive(path: Path) -> int | None:
    """The drive a path is on (st_dev of its nearest folder that's there), or None."""
    for p in (Path(path), *Path(path).parents):
        try:
            return p.stat().st_dev
        except OSError:
            continue
    return None


def _has_things(folder: Path) -> bool:
    try:
        return any(folder.iterdir())
    except OSError:
        return True


def problem(target: Path | None = None, root: Path | None = None) -> str:
    """Why this ReelForge can't move to target (its own folder, by default), as a sentence; "" when it can."""
    root = root or ROOT
    target = Path(os.path.abspath(str(target or home())))
    if P.test_copy():
        return "This is a test copy, and a test copy stays where it is (it never changes the computer)."
    if (root / ".git").exists():
        return "This is a git copy of ReelForge (one being worked on), so move it yourself, with git or by hand."
    if P.WINDOWS and (root / "unins000.exe").exists():
        return ("This copy came from the old Windows installer, and Windows' list of apps knows it by its folder, so "
                "it stays where it is.")
    if _same(target, root):
        return f"ReelForge is in {root} already."
    if _inside(target, root):
        return f"{target} is inside the ReelForge folder."
    if _inside(root, target):
        return f"The ReelForge folder is inside {target}."
    if target.exists() and (not target.is_dir() or _has_things(target)):
        return f"There's already something at {target}, so ReelForge can't go there."
    if _drive(target) != _drive(root):
        return (f"{target} is on another drive, and ReelForge only moves on the same drive (nothing is copied). Copy "
                "the folder there yourself, then run setup in the copy.")
    if P.WINDOWS and len(str(target)) > 160:
        return f"{target} is too long a path: Windows can't load some of Blender's files under it. Pick a shorter one."
    return ""


def _toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _system() -> dict[str, bool]:
    """Which of ReelForge's things outside its folder are this folder's now, each to point at the new place: the
    reelforge command, the icon, Windows Terminal's profile and the hourly stats read. None of them in a test copy
    or with STUDIO_DRY_SYSTEM, which never touch them."""
    out = {"command": False, "icon": False, "terminal": False, "stats": False}
    if P.dry_system():
        return out
    from . import command, shortcut, stats_schedule

    for key, check in (("command", lambda: command.status() == "on"), ("icon", shortcut.ours),
                       ("stats", lambda: stats_schedule.status() == "on")):
        try:
            out[key] = bool(check())
        except Exception:   # a check that can't be made (no scheduler, say): that thing is left as it is
            pass
    if P.WINDOWS:
        from . import terminal_profile

        out["terminal"] = terminal_profile.ours()
    return out


@dataclass
class Plan:
    """What a move does, worked out before anything changes (the dialog and the command say it, then do it)."""
    source: Path
    target: Path
    configs: list[tuple[Path, dict[str, str]]] = field(default_factory=list)  # config.toml -> {key: its full path}
    outside: list[Path] = field(default_factory=list)   # the folders the Publish tab reads outside ReelForge (stay)
    system: dict[str, bool] = field(default_factory=dict)


def plan(target: Path | None = None) -> Plan:
    """The move to target (its own folder, by default)."""
    target = Path(os.path.abspath(str(target or home())))
    out = Plan(ROOT, target, system=_system())
    for p in profiles.every():
        cfg, change = _toml(p.config), {}
        for key in KEYS:
            value = cfg.get(key)
            if not isinstance(value, str) or not value.strip():
                continue   # not set: its default is a folder inside the profile's, which moves with it
            raw = Path(value).expanduser()
            full = Path(os.path.normpath(str(raw if raw.is_absolute() else p.dashboard / raw)))
            if _inside(full, ROOT):
                if raw.is_absolute():   # written in full, inside the folder: it names the new place afterwards
                    change[key] = str(target / full.relative_to(ROOT))
                continue
            if not raw.is_absolute():   # starts from the dashboard folder, which moves: written in full instead
                change[key] = str(full)
            if not any(_same(full, f) for f in out.outside):
                out.outside.append(full)
        if change:
            out.configs.append((p.config, change))
    return out


def follows(system: dict[str, bool]) -> list[str]:
    """What follows the folder, in words."""
    icon = "the desktop icon" if P.WINDOWS else "ReelForge in Applications" if P.MAC else "ReelForge in your app menu"
    names = {"command": "the reelforge command", "icon": icon, "terminal": "Windows Terminal's ReelForge profile",
             "stats": "the hourly stats read"}
    return [names[k] for k in ("command", "icon", "terminal", "stats") if system.get(k)]


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def summary(p: Plan) -> list[str]:
    """The move in a few lines, for the command (the Settings tab's dialog says the same)."""
    lines = [f"Moving {KIT_NAME} into a folder of its own:", f"  from  {p.source}", f"  to    {p.target}",
             "Everything in it goes along in one step, on the same drive (nothing is copied): your channels, stats, "
             "log-ins, settings and videos, Blender and the rest."]
    if follows(p.system):
        them = _and(follows(p.system))
        lines.append(f"{them[0].upper()}{them[1:]} follow it.")
    if p.outside:
        lines.append("The Publish tab's folders outside ReelForge stay where they are:")
        lines += [f"  {f}" for f in p.outside]
    return lines


# ---------------------------------------------------------------- doing it

def others_open(mine: Path | None = None) -> bool:
    """Whether a ReelForge window (other than the one holding the lock `mine`) is open on any profile."""
    for p in profiles.every():
        try:
            locks = list(profiles.windows(p).glob("*.lock"))
        except OSError:
            continue
        if any(profiles.held(lock) for lock in locks if mine is None or not _same(lock, mine)):
            return True
    return False


def _write_configs(p: Plan) -> list[str]:
    """Write the Publish tab's outside folders in full, each config.toml in one step. Returns what went wrong."""
    from . import dashboard_config

    problems = []
    for path, change in p.configs:
        try:
            text = dashboard_config.set_keys(path.read_text(encoding="utf-8"), {"": change})
            tomllib.loads(text)    # never write a config the dashboard can't read
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            tmp.replace(path)
        except (OSError, tomllib.TOMLDecodeError) as e:
            problems.append(f"{P.rel(path)} couldn't be written ({e})")
    return problems


def prepare(p: Plan, reopen: bool = False) -> list[str]:
    """Everything before the rename: the Publish tab's outside folders written in full (they name the same places
    either way), the note --finish reads, and the target's parent folder. Returns what went wrong."""
    problems = _write_configs(p)
    if problems:
        return problems
    try:
        (ROOT / STATE).write_text(json.dumps({"from": str(p.source), "to": str(p.target), "system": p.system,
                                              "reopen": reopen, "asked": datetime.now().isoformat(timespec="seconds")})
                                  + "\n", encoding="utf-8")
        p.target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return [f"it couldn't get ready ({e})"]
    return []


def _undo() -> None:
    try:
        (ROOT / STATE).unlink()
    except OSError:
        pass


def rename(p: Plan, wait: float = 10) -> str | None:
    """Rename the folder (an empty folder at the target goes first), trying again for a few seconds while something
    has a file in it open. Returns what went wrong, or None. On Windows only once ReelForge has closed."""
    end = time.monotonic() + wait
    while True:
        try:
            if p.target.is_dir() and not _has_things(p.target):
                p.target.rmdir()
            os.rename(p.source, p.target)
            return None
        except OSError as e:
            if time.monotonic() >= end:
                return e.strerror or str(e)
            time.sleep(0.5)


def repair_venv(old: Path, new: Path) -> None:
    """A .venv made from a Python inside the folder (setup's private one in tools/python, on a Mac or Linux) names
    that Python in full: in its pyvenv.cfg and, outside Windows, in the links in .venv/bin and the first line of its
    scripts. Point them at the new place (the rest of .venv works wherever it is)."""
    venv = new / ".venv"
    cfg = venv / "pyvenv.cfg"
    try:
        text = cfg.read_text(encoding="utf-8")
        keys = ("home", "executable", "command")
        fixed = "".join(line.replace(str(old), str(new)) if line.split("=", 1)[0].strip() in keys else line
                        for line in text.splitlines(keepends=True))
        if fixed != text:
            cfg.write_text(fixed, encoding="utf-8")
    except OSError:
        pass
    if P.WINDOWS:
        return
    try:
        files = list((venv / "bin").iterdir())
    except OSError:
        return
    for f in files:
        try:
            if f.is_symlink():
                dest = os.readlink(f)
                if os.path.isabs(dest) and _inside(Path(dest), old):
                    f.unlink()
                    f.symlink_to(str(new) + dest[len(str(old)):])
            elif f.is_file() and f.stat().st_size < 1 << 16:
                data = f.read_bytes()
                first, nl, rest = data.partition(b"\n")
                if first.startswith(b"#!") and str(old).encode() in first:
                    f.write_bytes(first.replace(str(old).encode(), str(new).encode()) + nl + rest)
        except OSError:
            pass


# The small window that renames the folder on Windows once ReelForge has closed, then runs --finish from the new
# place, and with -Open starts ReelForge there. With -NoPause (the window's own move, or --yes) it closes itself.
WINDOWS_MOVE = r"""
param([string]$From, [string]$To, [switch]$Open, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = 'Moving ReelForge' } catch {}
$env:PYTHONUTF8 = '1'
function Done($code) {
  Write-Host ''
  if (-not $NoPause) { Read-Host 'Press Enter to close this window' | Out-Null }
  elseif ($code -ne 0) { Start-Sleep -Seconds 30 }   # long enough to read what went wrong
  try { [IO.File]::Delete($PSCommandPath) } catch {}   # this script, written to the temp folder for this one run
  exit $code
}
Write-Host 'Moving ReelForge into a folder of its own:'
Write-Host "  from  $From"
Write-Host "  to    $To"
Write-Host ''
Write-Host 'Waiting for ReelForge to close (close any window or terminal still open in its folder)...'
$moved = $false
for ($i = 0; $i -lt 600 -and -not $moved; $i++) {
  try {
    if ([IO.Directory]::Exists($To) -and @([IO.Directory]::GetFileSystemEntries($To)).Count -eq 0) {
      [IO.Directory]::Delete($To)   # an empty folder waiting for it
    }
    [IO.Directory]::Move($From, $To)
    $moved = $true
  } catch {
    if ($i -eq 15) { Write-Host 'Still waiting: a terminal, Claude Code, Codex or Explorer has something in it open?' }
    Start-Sleep -Milliseconds 1000
  }
}
if (-not $moved) {
  try { [IO.File]::Delete([IO.Path]::Combine($From, '.reelforge-moving.json')) } catch {}
  Write-Host ''
  Write-Host "ReelForge's folder is still in use, so it stayed where it is: $From"
  Write-Host 'Close everything open in it, then move it again (Move on the Settings tab, or reelforge move).'
  if ($Open) { Start-Process -FilePath ([IO.Path]::Combine($From, 'ReelForge.bat')) -WorkingDirectory $From }
  Done 1
}
Write-Host 'Moved. Pointing everything at the new folder...'
Write-Host ''
# A .venv made from a Python inside the folder names it in pyvenv.cfg, and couldn't start until that follows too.
$cfg = [IO.Path]::Combine($To, '.venv', 'pyvenv.cfg')
if ([IO.File]::Exists($cfg)) {
  $lines = [IO.File]::ReadAllLines($cfg)
  if ($lines | Where-Object { $_ -match '^\s*home\s*=' -and $_.Contains($From) }) {
    $lines = $lines | ForEach-Object {
      if ($_ -match '^\s*(home|executable|command)\s*=') { $_.Replace($From, $To) } else { $_ }
    }
    [IO.File]::WriteAllLines($cfg, [string[]]$lines)
  }
}
$code = 1
try {
  $py = [IO.Path]::Combine($To, '.venv', 'Scripts', 'python.exe')
  & $py ([IO.Path]::Combine($To, 'bin', 'reelforge.py')) move --finish
  $code = $LASTEXITCODE
} catch {
  Write-Host "The last step didn't run ($($_.Exception.Message)). Run setup in the new folder to finish."
}
if ($Open) { Start-Process -FilePath ([IO.Path]::Combine($To, 'ReelForge.bat')) -WorkingDirectory $To }
Done $code
"""


def _window(p: Plan, reopen: bool, pause: bool) -> str | None:
    """Start the small window that moves the folder once ReelForge has closed (Windows). Returns what went wrong."""
    script = Path(tempfile.gettempdir()) / f"reelforge-move-{datetime.now():%Y-%m-%d-%H%M%S}-{os.getpid()}.ps1"
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-From", str(p.source),
            "-To", str(p.target), *(["-Open"] if reopen else []), *([] if pause else ["-NoPause"])]
    try:
        script.write_text(WINDOWS_MOVE, encoding="utf-8-sig")
        # No stdin/stdout/stderr: the window reads and writes its own console (as studio/reset.py's bin_folder).
        subprocess.Popen(args, cwd=tempfile.gettempdir(), creationflags=flags, close_fds=True)
    except OSError as e:
        return f"the window that moves it couldn't start ({e})"
    return None


def go(p: Plan, reopen: bool = False, pause: bool = True, say=print) -> tuple[int, bool]:
    """Move the folder as planned (problem() said it can, and no window is open). On Windows a small window does it
    once this process has closed; elsewhere it's done here and now, then --finish runs from the new place, and with
    reopen ReelForge opens there in place of this process. Returns (the exit code, whether the folder has moved)."""
    problems = prepare(p, reopen)
    if problems:
        _undo()
        say(f"{KIT_NAME} didn't move, and nothing else changed: {'; '.join(problems)}.")
        return 1, False
    if P.WINDOWS:
        err = _window(p, reopen, pause)
        if err:
            _undo()
            say(f"{KIT_NAME} didn't move: {err}.")
            return 1, False
        say(f"A small window moves {KIT_NAME} as soon as it has closed (it waits while anything still has a file in "
            "the folder open), then points everything at the new folder"
            + (" and opens ReelForge again." if reopen else "."))
        return 0, False
    os.chdir(p.target.parent)   # not inside the folder that's moving
    err = rename(p)
    if err:
        _undo()
        say(f"{KIT_NAME} didn't move ({err}), and nothing else changed.")
        return 1, False
    repair_venv(p.source, p.target)
    code = subprocess.run([str(p.target / ".venv" / "bin" / "python"), str(p.target / "bin" / "reelforge.py"), "move",
                           "--finish"], cwd=p.target).returncode
    launcher = p.target / "bin" / "reelforge"
    if reopen and launcher.is_file():
        sys.stdout.flush()
        try:
            os.execv("/bin/sh", ["/bin/sh", str(launcher), "settings"])   # the new place's launcher, on Settings
        except OSError as e:
            say(f"Open ReelForge again from {p.target} ({e}).")
    return code, True


# ---------------------------------------------------------------- after the move, from the new place

def finish(say=print) -> int:
    """Point what named the old place at this one, as the note the move left in the folder says, and leave the next
    window a note that it moved. Returns the exit code."""
    state = ROOT / STATE
    try:
        job = json.loads(state.read_text(encoding="utf-8"))
        old, new = Path(job["from"]), Path(job["to"])
    except (OSError, ValueError, KeyError, TypeError):
        say(f"There's no move to finish here ({state} isn't there).")
        return 1
    if not _same(new, ROOT) or _same(old, ROOT):
        say(f"{KIT_NAME} hasn't moved to {new}, so there's nothing to finish.")
        return 1
    repair_venv(old, new)
    say(f"{KIT_NAME} is in {new} now.")
    problems: list[str] = []
    system = job.get("system") or {}
    if not P.dry_system():
        from . import command, shortcut, stats_schedule, terminal_profile

        steps = (("command", "the reelforge command", lambda: command.follow(old)),
                 ("icon", "the icon", lambda: f"ReelForge's icon is at {shortcut.make()}."),
                 ("terminal", "Windows Terminal's profile", terminal_profile.ensure),
                 ("stats", "the hourly stats read", stats_schedule.enable))
        for key, name, step in steps:
            if system.get(key):
                try:
                    say("  " + step())
                except Exception as e:
                    problems.append(f"{name} ({e})")
    if problems:
        say("These couldn't follow it: " + "; ".join(problems) + ". Run setup in the new folder to fix them.")
    try:
        marker = ROOT / MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"from": str(old), "to": str(new), "ts": time.time(), "problems": problems}),
                          encoding="utf-8")
        state.unlink()
    except OSError:
        pass
    return 1 if problems else 0


def take_marker(root: Path | None = None) -> dict | None:
    """Where the last move took ReelForge ({from, to, problems}), once: the next window says so."""
    marker = (root or ROOT) / MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        marker.unlink()
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def finish_leftover() -> None:
    """Each time ReelForge starts: a move whose last step never ran (its window was closed part way, say) finishes
    now, from the new place; the note of one that never happened goes after a day."""
    state = ROOT / STATE
    if not state.is_file():
        return
    try:
        job = json.loads(state.read_text(encoding="utf-8"))
        moved = _same(Path(job["to"]), ROOT) and not _same(Path(job["from"]), ROOT)
        asked = datetime.fromisoformat(job["asked"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return
    if moved:
        finish()
    elif time.time() - asked > STALE:
        _undo()


# ---------------------------------------------------------------- asked for by the window

def request(target: Path | None = None) -> None:
    """The window asks for a move; the launcher starts it as it starts ReelForge again (studio/reset.py pending)."""
    from . import reset

    data = {"do": "move", "to": str(target or home()), "asked": datetime.now().isoformat(timespec="seconds")}
    reset.PENDING.write_text(json.dumps(data) + "\n", encoding="utf-8")


def from_window(job: dict) -> list[str] | int:
    """The move the window just asked for (it closed for it). A list: open ReelForge with these arguments (on the
    Settings tab when it couldn't move); otherwise the exit code to stop with."""
    from . import reset

    target = Path(job.get("to") or home())
    reason = problem(target) or ("Another ReelForge window is open: close it, then move ReelForge again."
                                 if others_open() else "")
    if reason:
        print(f"{KIT_NAME} didn't move: {reason}\n")
        return reset._open_again()
    reset._wait_for_reads(print)
    p = plan(target)
    print("\n".join(summary(p)) + "\n")
    code, moved = go(p, reopen=True, pause=False)
    if code and not moved:
        return reset._open_again()
    return code


# ---------------------------------------------------------------- the command

def main(argv: list[str]) -> int:
    if argv[:1] == ["--finish"]:
        return finish()
    yes = "--yes" in argv or "-y" in argv
    words = [a for a in argv if a not in ("--yes", "-y")]
    if len(words) > 1 or any(w.startswith("-") for w in words):
        print(f"usage: reelforge move [FOLDER] [--yes]   (FOLDER: where it goes; by default its own folder, {home()})")
        return 2
    target = Path(os.path.abspath(os.path.expanduser(words[0]))) if words else home()
    if not words and at_home():
        print(f"{KIT_NAME} is in its own folder already: {ROOT}")
        return 0
    reason = problem(target)
    if reason:
        print(f"{KIT_NAME} can't move: {reason}")
        return 1
    if others_open():
        print(f"{KIT_NAME} is open: close it (or use Move on its Settings tab), then try again.")
        return 1
    p = plan(target)
    print("\n".join(summary(p)) + "\n")
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("Run it in a terminal to confirm, or add --yes.")
            return 2
        try:
            answer = input("Move it? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Nothing was changed.")
            return 1
    from . import reset

    reset._wait_for_reads(print)
    if others_open():   # one opened in the meantime
        print(f"{KIT_NAME} was opened in the meantime: close it, then try again. Nothing was changed.")
        return 1
    code, moved = go(p, pause=not yes)
    if code == 0 and P.WINDOWS and _inside(Path.cwd(), ROOT):
        print(f"\nThis terminal is in the {KIT_NAME} folder, which keeps it from moving: close the terminal, or cd out "
              "of the folder.")
    elif moved:
        print("\nOpen it as usual: reelforge, or its icon.")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
