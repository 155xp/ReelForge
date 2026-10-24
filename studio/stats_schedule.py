"""Keep reading your stats every hour, even when ReelForge is closed.

  python -m studio stats on       start the hourly background job
  python -m studio stats off      stop it
  python -m studio stats          is it on?

Windows: a Task Scheduler task ("ReelForge stats") runs dashboard/refresh.pyw with the kit's own Python, without a window,
while you're signed in. macOS: a launchd agent. Linux: a crontab line. Your computer has to be on; hours it was off
or asleep stay empty on the charts, and what was gained meanwhile still counts in the totals. Uninstalling ReelForge
removes the job.

A computer has one such job, and it belongs to the ReelForge folder whose refresh.pyw it runs. Another copy (a test
install, say) never takes it over or turns it off while that folder is still there; once the folder is gone (moved
or deleted), turning the job on from the new copy moves it there. A test copy (TEST-COPY.txt in its folder) never
touches the job at all.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from . import paths as P

TASK = "ReelForge stats"
MAC_LABEL = "com.reelforge.stats"
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


def _job() -> Path | None:
    """The refresh script the hourly job runs, in whichever ReelForge folder turned it on (an empty Path() if that
    can't be read), or None when there's no job. Raises OSError where there's no scheduler to ask (no crontab)."""
    if P.WINDOWS:
        r = _ps("[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "   # paths may not be ASCII
                f"$t = Get-ScheduledTask -TaskName {_q(TASK)} -ErrorAction SilentlyContinue; "
                "if ($t) { 'job:' + $t.Actions[0].Arguments }")
        out = r.stdout.strip().lstrip("﻿")
        return Path(out[4:].strip().strip('"')) if out.startswith("job:") else None
    if P.MAC:
        if not _plist().exists():
            return None
        import plistlib

        try:
            args = plistlib.loads(_plist().read_bytes()).get("ProgramArguments") or []
        except Exception:  # an unreadable plist is still a job
            return Path()
        return Path(args[-1]) if args else Path()
    out = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    line = next((ln for ln in out.splitlines() if CRON_MARK in ln), None)
    if line is None:
        return None
    m = re.search(r'"([^"]*refresh\.pyw)"', line)
    return Path(m.group(1)) if m else Path()


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
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{MAC_LABEL}</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{script}</string></array>
  <key>WorkingDirectory</key><string>{P.DASHBOARD}</string>
  <key>StartInterval</key><integer>{minutes * 60}</integer>
</dict></plist>
""", encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True)
        return f"Your stats will update every {minutes} minutes while this Mac is awake."
    line = f'0 * * * * cd "{P.DASHBOARD}" && "{py}" "{script}" {CRON_MARK}'
    try:
        old = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [ln for ln in old.splitlines() if CRON_MARK not in ln]
        subprocess.run(["crontab", "-"], input="\n".join(keep + [line]) + "\n", text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        return f"Couldn't add the crontab line ({e}). Add it yourself: {line}"
    return "Your stats will update every hour while this computer is on."


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
            subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True)
            plist.unlink()
        return "Background stats are off."
    try:
        old = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [ln for ln in old.splitlines() if CRON_MARK not in ln]
        subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n", text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pass
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
