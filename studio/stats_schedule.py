"""Keep reading your stats every hour, even when ReelForge is closed.

  python -m studio stats on       start the hourly background job
  python -m studio stats off      stop it
  python -m studio stats          is it on?

Windows: a Task Scheduler task ("ReelForge stats") runs dashboard/refresh.pyw with the kit's own Python, without a window,
while you're signed in. macOS: a launchd agent (~/Library/LaunchAgents/com.reelforge.stats.plist), while you're
signed in. Linux: a systemd user timer (reelforge-stats.timer) while you're signed in, or a crontab line where there's
no systemd. Your computer has to be on; hours it was off or asleep are filled in on the charts with an estimate
(hatched), and what was gained meanwhile still counts in the totals. reelforge stats off removes the job.

A computer has one such job, and it belongs to the ReelForge folder whose refresh.pyw it runs. Another copy (a test
install, say) never takes it over or turns it off while that folder is still there; once the folder is gone (moved
or deleted), turning the job on from the new copy moves it there. A test copy (TEST-COPY.txt in its folder) never
touches the job at all.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths as P

TASK = "ReelForge stats"
MAC_LABEL = "com.reelforge.stats"
UNIT = "reelforge-stats"
CRON_MARK = "# reelforge-stats"
ELSEWHERE = "Another ReelForge folder"  # how enable() starts when the job belongs to another copy
TEST_COPY = "Background stats are off in a test copy"  # how enable() starts in a test copy, which leaves the job alone
TEST_COPY_NOTE = f"{TEST_COPY} (the hourly job stays with your main ReelForge folder)."


def _python(windowless: bool = True) -> Path:
    if P.WINDOWS:
        exe = "pythonw.exe" if windowless else "python.exe"
        return P.ROOT / ".venv" / "Scripts" / exe
    return P.ROOT / ".venv" / "bin" / "python"


def _refresh_script() -> Path:
    return P.DASHBOARD / "refresh.pyw"


def _dry() -> bool:
    """STUDIO_DRY_SYSTEM=1 (tests) or a test copy: report what would happen without touching the system's
    scheduler."""
    return P.dry_system()


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _q(text: str) -> str:
    """A PowerShell single-quoted string (paths may contain apostrophes)."""
    return "'" + str(text).replace("'", "''") + "'"


def _plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def _units() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")) / "systemd" / "user"


def _systemd() -> bool:
    """Whether this Linux session has a systemd user manager to run timers (most desktops do; containers and
    distributions without systemd don't)."""
    if not shutil.which("systemctl") or not Path("/run/systemd/system").is_dir():
        return False
    try:
        return subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30)


def _crontab() -> str:
    """The crontab's lines ("" for none). Raises OSError when there's no crontab command."""
    return subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout


def _set_crontab(lines: list[str]) -> None:
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n" if lines else "", text=True, check=True)


def _script_in(words: list[str]) -> Path:
    """The refresh script among a command line's words (an empty Path() if it isn't there)."""
    return next((Path(w) for w in words if w.endswith("refresh.pyw")), Path())


def _job() -> Path | None:
    """The refresh script the hourly job runs, in whichever ReelForge folder turned it on (an empty Path() if that
    can't be read), or None when there's no job. Raises OSError where there's no scheduler to ask (no systemd and no
    crontab)."""
    if P.WINDOWS:
        r = _ps("[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "   # paths may not be ASCII
                f"$t = Get-ScheduledTask -TaskName {_q(TASK)} -ErrorAction SilentlyContinue; "
                "if ($t) { 'job:' + $t.Actions[0].Arguments }")
        out = r.stdout.strip().lstrip("﻿")
        return Path(out[4:].strip().strip('"')) if out.startswith("job:") else None
    if P.MAC:
        if not _plist().exists():
            return None
        try:
            args = plistlib.loads(_plist().read_bytes()).get("ProgramArguments") or []
        except Exception:  # an unreadable plist is still a job
            return Path()
        return Path(args[-1]) if args else Path()
    service = _units() / f"{UNIT}.service"
    if service.exists():
        line = next((ln for ln in service.read_text(encoding="utf-8").splitlines() if ln.startswith("ExecStart=")), "")
        try:
            return _script_in(shlex.split(line.split("=", 1)[-1].replace("%%", "%").replace("$$", "$")))
        except ValueError:
            return Path()
    if not _systemd() and not shutil.which("crontab"):
        raise OSError("no systemd user manager and no crontab")
    out = _crontab() if shutil.which("crontab") else ""
    line = next((ln for ln in out.splitlines() if CRON_MARK in ln), None)
    if line is None:
        return None
    try:
        return _script_in(shlex.split(line.replace("\\%", "%"), comments=True))
    except ValueError:
        return Path()


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _other_folder() -> Path | None:
    """The other ReelForge folder the job belongs to, while that folder is still there. None when the job is this
    folder's, when there's none, or when its folder has gone (then this copy may take the job over)."""
    job = _job()
    if job is None or _same(job, _refresh_script()) or not job.name or not job.is_file():
        return None
    return job.parent.parent


def status() -> str:
    """'on' (this folder's job), 'other' (another ReelForge folder's), 'off' or 'unsupported'."""
    if _dry():
        return "off"
    try:
        job = _job()
    except OSError:
        return "unsupported"
    if job is None:
        return "off"
    return "on" if _same(job, _refresh_script()) else "other"


def mac_plist(py: Path, script: Path, minutes: int = 60) -> bytes:
    return plistlib.dumps({
        "Label": MAC_LABEL,
        "ProgramArguments": [str(py), str(script)],
        "WorkingDirectory": str(P.DASHBOARD),
        "StartInterval": minutes * 60,
        "ProcessType": "Background",
    })


def systemd_units(py: Path, script: Path, minutes: int = 60) -> dict[str, str]:
    """The service that reads the stats once and the timer that starts it: two minutes after you sign in, then every
    `minutes`. In unit files % starts a specifier and $ a variable, so they're written %% and $$."""
    def q(path: Path) -> str:
        return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'

    service = (f"[Unit]\nDescription=ReelForge: read your TikTok, YouTube, Instagram and X stats\n\n"
               f"[Service]\nType=oneshot\nWorkingDirectory={str(P.DASHBOARD).replace('%', '%%')}\n"
               f"ExecStart={q(py)} {q(script)}\nTimeoutStartSec=20min\n")
    timer = (f"[Unit]\nDescription=ReelForge: read your stats every {minutes} minutes\n\n"
             f"[Timer]\nOnStartupSec=2min\nOnUnitActiveSec={minutes}min\n\n[Install]\nWantedBy=timers.target\n")
    return {f"{UNIT}.service": service, f"{UNIT}.timer": timer}


def cron_line(py: Path, script: Path) -> str:
    """The crontab line: paths quoted for the shell, and % (which cron turns into a new line) escaped."""
    q = lambda p: shlex.quote(str(p)).replace("%", "\\%")  # noqa: E731
    return f"0 * * * * cd {q(P.DASHBOARD)} && {q(py)} {q(script)} {CRON_MARK}"


def enable(minutes: int = 60) -> str:
    """Start (or restart) the hourly job. Returns a sentence saying what happened."""
    py, script = _python(), _refresh_script()
    if P.test_copy():
        return TEST_COPY_NOTE
    if _dry():
        return f"(dry run) would run {script.name} every {minutes} minutes"
    if not py.exists() or not script.exists():
        return "Background stats need setup to have finished first (run setup again)."
    try:
        other = _other_folder()
    except OSError:
        other = None
    if other is not None:
        there, here = (folder / "bin" / ("reelforge.cmd" if P.WINDOWS else "reelforge") for folder in (other, P.ROOT))
        return (f"{ELSEWHERE} already reads your stats every hour ({other}), so it's left as it is. To move the job "
                f'here: "{there}" stats off, then "{here}" stats on')
    if P.WINDOWS:
        ps = f"""
$a = New-ScheduledTaskAction -Execute {_q(py)} -Argument {_q('"' + str(script) + '"')} -WorkingDirectory {_q(P.DASHBOARD)}
$t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes {minutes})
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
     -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName {_q(TASK)} -Action $a -Trigger $t -Settings $s -Force `
     -Description 'Reads your TikTok, YouTube, Instagram and X stats for ReelForge while it is closed.' | Out-Null
'ok'
"""
        r = _ps(ps)
        if r.returncode != 0 or "ok" not in r.stdout:
            return "Couldn't create the background job: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1]
        return f"Your stats will update every {minutes} minutes while this computer is on, even with ReelForge closed."
    if P.MAC:
        plist = _plist()
        plist.parent.mkdir(parents=True, exist_ok=True)
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{MAC_LABEL}"], capture_output=True)
        plist.write_bytes(mac_plist(py, script, minutes))
        if subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True).returncode != 0:
            subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True)   # older macOS
        return f"Your stats will update every {minutes} minutes while this Mac is awake, even with ReelForge closed."
    if _systemd():
        units = _units()
        units.mkdir(parents=True, exist_ok=True)
        for name, text in systemd_units(py, script, minutes).items():
            (units / name).write_text(text, encoding="utf-8")
        _systemctl("daemon-reload")
        r = _systemctl("enable", "--now", f"{UNIT}.timer")
        if r.returncode != 0:
            return "Couldn't start the background job: " + ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1]
        _drop_cron_line()      # the crontab line earlier versions used
        return f"Your stats will update every {minutes} minutes while you're signed in, even with ReelForge closed."
    line = cron_line(py, script)
    try:
        keep = [ln for ln in _crontab().splitlines() if CRON_MARK not in ln]
        _set_crontab(keep + [line])
    except (OSError, subprocess.CalledProcessError) as e:
        return f"Couldn't add the crontab line ({e}). Add it yourself: {line}"
    return "Your stats will update every hour while this computer is on, even with ReelForge closed."


def _drop_cron_line() -> None:
    if not shutil.which("crontab"):
        return
    try:
        old = _crontab()
        keep = [ln for ln in old.splitlines() if CRON_MARK not in ln]
        if len(keep) != len(old.splitlines()):
            _set_crontab(keep)
    except (OSError, subprocess.CalledProcessError):
        pass


def disable() -> str:
    """Stop this folder's hourly job (one that belongs to another ReelForge folder stays). Returns a sentence."""
    if P.test_copy():
        return TEST_COPY_NOTE
    if _dry():
        return "(dry run) would remove the background job"
    try:
        other = _other_folder()
    except OSError:
        other = None
    if other is not None:
        return f"Background stats are off for this folder. The hourly job belongs to {other} and keeps running there."
    if P.WINDOWS:
        _ps(f"Unregister-ScheduledTask -TaskName {_q(TASK)} -Confirm:$false -ErrorAction SilentlyContinue")
        return "Background stats are off."
    if P.MAC:
        plist = _plist()
        if plist.exists():
            if subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{MAC_LABEL}"],
                              capture_output=True).returncode != 0:
                subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True)
            plist.unlink()
        return "Background stats are off."
    units = _units()
    if (units / f"{UNIT}.timer").exists() or (units / f"{UNIT}.service").exists():
        if shutil.which("systemctl"):
            _systemctl("disable", "--now", f"{UNIT}.timer")
        for name in (f"{UNIT}.timer", f"{UNIT}.service"):
            (units / name).unlink(missing_ok=True)
        if shutil.which("systemctl"):
            _systemctl("daemon-reload")
    _drop_cron_line()
    return "Background stats are off."


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "on":
        print(enable())
    elif cmd == "off":
        print(disable())
    elif cmd == "status" and P.test_copy():
        print(TEST_COPY_NOTE)
    elif cmd == "status":
        state = status()
        if state == "other":
            other = _other_folder()
            state = (f"off here; the hourly job belongs to {other}" if other else
                     "off here; the hourly job belongs to a ReelForge folder that's gone (reelforge stats on moves it "
                     "here)")
        print(f"Background stats: {state}")
    else:
        print("usage: python -m studio stats [on|off]")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
