"""Keep reading your stats every hour, even when ReelForge is closed.

  python -m studio stats on       start the hourly background job
  python -m studio stats off      stop it
  python -m studio stats          is it on?

Windows: a Task Scheduler task ("ReelForge stats") runs dashboard/refresh.pyw with the kit's own Python, without a window,
while you're signed in. macOS: a launchd agent. Linux: a crontab line. Your computer has to be on; hours it was off
or asleep stay empty on the charts, and what was gained meanwhile still counts in the totals. Uninstalling ReelForge
removes the job.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import paths as P

TASK = "ReelForge stats"
MAC_LABEL = "com.reelforge.stats"
CRON_MARK = "# reelforge-stats"


def _python(windowless: bool = True) -> Path:
    if P.WINDOWS:
        exe = "pythonw.exe" if windowless else "python.exe"
        return P.ROOT / ".venv" / "Scripts" / exe
    return P.ROOT / ".venv" / "bin" / "python"


def _refresh_script() -> Path:
    return P.DASHBOARD / "refresh.pyw"


def _dry() -> bool:
    """STUDIO_DRY_SYSTEM=1: report what would happen without touching the system's scheduler (tests)."""
    return os.environ.get("STUDIO_DRY_SYSTEM", "").strip() in ("1", "true", "yes")


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _q(text: str) -> str:
    """A PowerShell single-quoted string (paths may contain apostrophes)."""
    return "'" + str(text).replace("'", "''") + "'"


def status() -> str:
    """'on', 'off' or 'unsupported'."""
    if _dry():
        return "off"
    if P.WINDOWS:
        r = _ps(f"if (Get-ScheduledTask -TaskName {_q(TASK)} -ErrorAction SilentlyContinue) {{ 'on' }} else {{ 'off' }}")
        return r.stdout.strip() or "off"
    if P.MAC:
        return "on" if (Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist").exists() else "off"
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except OSError:
        return "unsupported"
    return "on" if CRON_MARK in out else "off"


def enable(minutes: int = 60) -> str:
    """Start (or restart) the hourly job. Returns a sentence saying what happened."""
    py, script = _python(), _refresh_script()
    if _dry():
        return f"(dry run) would run {script.name} every {minutes} minutes"
    if not py.exists() or not script.exists():
        return "Background stats need setup to have finished first (run setup again)."
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
        plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
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
    if _dry():
        return "(dry run) would remove the background job"
    if P.WINDOWS:
        _ps(f"Unregister-ScheduledTask -TaskName {_q(TASK)} -Confirm:$false -ErrorAction SilentlyContinue")
        return "Background stats are off."
    if P.MAC:
        plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
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
    elif cmd == "status":
        print(f"Background stats: {status()}")
    else:
        print("usage: python -m studio stats [on|off]")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
