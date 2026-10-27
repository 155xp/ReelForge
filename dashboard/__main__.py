"""reelforge [1-8 | a tab's name | notifications | refresh] [--demo]      (also: python -m dashboard ...)

  reelforge                ReelForge on the Overview tab
  reelforge 4              straight to a tab: 1 Overview, 2 Videos, 3 Compare, 4 Publish, 5 Accounts, 6 Updates,
                           7 Settings, 8 Stats (reelforge totals: reelforge stats is the hourly job)
  reelforge publish        the same, by name
  reelforge notifications  with the notifications drawer open
  reelforge refresh        read every profile's stats once, save them and exit (the hourly background job)
  reelforge --demo         try it on made-up data; nothing is read or saved

The window opens on the profile (the channel) you had open last; reelforge -p NAME picks one (see studio/profiles.py).

Exit codes: 0 fine, 2 a word it doesn't know, 3 the kit's Python packages are missing (run setup), 75 ReelForge
updated itself and the launcher should start it again.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import httpx  # noqa: F401
except ImportError:
    sys.exit(3)  # the launchers take exit code 3 to mean "repair the environment"

from . import config, db, notify, sync  # noqa: E402
from .tabs import DRAWER_WORDS, TAB_IDS, TABS, USAGE, tab_for  # noqa: E402,F401


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reelforge", usage=USAGE,
                                     description="ReelForge: your stats on TikTok, YouTube, Instagram and X, the "
                                                 "Publish tab, notifications and updates.")
    parser.add_argument("--demo", action="store_true", help="try ReelForge on made-up data; nothing is read or saved")
    parser.add_argument("what", nargs="?", default="", help="a tab (1-8 or its name), notifications, or refresh")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    word = args.what.strip().lower()
    if word and word != "refresh" and tab_for(word) is None:
        print(f"reelforge doesn't know {args.what!r}. Use: {USAGE}")
        return 2

    try:
        cfg = config.load_config()
    except config.ConfigError as e:
        print(f"ReelForge can't start: {e}")
        return 2

    if word == "refresh":  # only the connected platforms are read (Platform.connected)
        return refresh_profiles(args.demo)

    # The window is the OpenTUI app in ui/; it runs dashboard/service.py through studio/bridge.py, on the profile asked
    # for (reelforge -p NAME), else the one you had open last.
    from studio import profiles, tui, ui

    if not profiles.get(os.environ.get(profiles.ENV)):
        profiles.use(profiles.last())

    tui.set_title("ReelForge TEST" if (config.APP_DIR.parent / "TEST-COPY.txt").exists() else "ReelForge")
    if sys.platform == "win32":
        threading.Thread(target=_terminal_profile, daemon=True).start()
    # No tab asked for: the Overview, or Accounts while nothing is connected (Dashboard.open).
    code, _ = ui.run("dashboard", {"tab": tab_for(word), "drawer": word in DRAWER_WORDS, "demo": args.demo})
    if code == 75 and not (config.APP_DIR.parent / ".reelforge-pending.json").exists():  # not a reset or uninstall
        print("ReelForge updated itself; starting it again…")
    return code


def load_platforms(demo: bool = False, only_demos: bool = False, unconnected=()) -> tuple[dict, dict]:
    """The settings and every platform (only the connected ones show: Platform.connected), with the stats database
    open: the real one, or for the demo a fresh one of made-up stats (only_demos: the Publish tab lists just the kit's
    own demo videos, and unconnected: the demo platforms left unconnected, for the README's pictures)."""
    cfg = config.load_config()
    if demo:
        from . import demo as demo_data

        path = config.DATA_DIR / "demo.db"
        for suffix in ("", "-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        db.init(path)
        if only_demos:
            from . import videos

            names = {p.parent.name for p in (config.APP_DIR.parent / "examples").glob("*/episode.json")}
            every = videos.find
            videos.find = lambda c: [f for f in every(c) if f.stem in names]
        demo_data.seed(video=demo_data.newest_video(cfg))
        return cfg, demo_data.platforms(unconnected)
    from .platforms import build

    db.init(config.DB_PATH)
    return cfg, build(cfg)


def _terminal_profile() -> None:
    """The anvil on ReelForge's tab in Windows Terminal (studio/terminal_profile.py), checked in the background each
    time ReelForge opens: a nicety, never a reason not to open."""
    try:
        from studio import terminal_profile

        terminal_profile.ensure()
    except Exception:
        pass


JOB_BUDGET = 15 * 60  # seconds the hourly job spends on every profile together: the scheduler stops it at 20 minutes


def refresh_profiles(demo: bool = False) -> int:
    """`reelforge refresh`: one stats read of every profile (or just the one asked for: reelforge -p NAME refresh).
    Each profile is read in a process of its own, one after the other, as though each had its own job; a profile whose
    settings turn background stats off is left out. With one profile it's read here, as it always was."""
    from studio import profiles
    from studio import settings as S

    asked = profiles.get(os.environ.get(profiles.ENV))
    if demo or asked is not None or not profiles.several():
        from .platforms import connected

        cfg, every = load_platforms(demo)
        return refresh(connected(every, db.stored_platforms()), cfg, demo=demo)
    root = Path(__file__).resolve().parent.parent
    end = time.monotonic() + JOB_BUDGET
    code = 0
    for p in profiles.every():
        if p.onboarded and not S.load(p.settings)["platforms"].get("background_stats", True):
            continue
        left = int(end - time.monotonic())
        if left < 30:
            print(f"{p.name}: left for the next run (this one ran out of time)")
            code = max(code, 1)
            continue
        print(f"{p.name}:", flush=True)
        env = {**os.environ, profiles.ENV: p.key, "REELFORGE_REFRESH_WAIT": str(min(sync.WAIT, max(left - 60, 0)))}
        try:
            code = max(code, subprocess.call([sys.executable, "-m", "dashboard", "refresh"], cwd=root, env=env,
                                             timeout=left))
        except subprocess.TimeoutExpired:
            code = max(code, 1)
    return code


def refresh(platforms: dict, cfg: dict, demo: bool = False) -> int:
    """One stats read, then new videos and (every few hours) the update check, all saved for the next look. Open
    ReelForge windows show what it read."""
    result = sync.refresh(platforms, cfg, manual=True, who="job")
    db.compact()
    if not demo:
        for extra in (lambda: notify.check_videos(cfg), _check_updates):
            try:
                extra()
            except Exception:
                pass  # extras: a hiccup here never fails the read
    if result.busy:  # another ReelForge has been reading all along: it saves what it reads
        done = f"nothing ({result.waited or sync.WHO['window']} was still reading after {sync.WAIT // 60} minutes)"
    elif result.done:
        done = ", ".join(result.done)
    else:
        done = "nothing due" + (f" ({result.waited} had just read them)" if result.waited else "")
    lines = [f"refreshed: {done}", *("error: " + e for e in result.errors)]
    print("\n".join(lines))
    # A scheduled refresh has no window to read, so it also keeps a short log.
    log = config.DATA_DIR / "refresh.log"
    try:
        old = log.read_text("utf-8").splitlines()[-200:] if log.exists() else []
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        log.write_text("\n".join([*old, *(f"{stamp}  {line}" for line in lines)]) + "\n", "utf-8")
    except OSError:
        pass
    return 1 if result.errors or result.busy else 0


def _check_updates() -> None:
    """Ask GitHub about a newer ReelForge at most every 6 hours, so the bell can say so before you open the app."""
    from .service import UPDATE_EVERY_H, _hours_since

    try:
        from studio import KIT_VERSION
        from studio import update as kit_update
    except Exception:
        return
    info = db.get_meta("update_check")
    if info and info.get("current") == KIT_VERSION and _hours_since(info.get("checked")) < UPDATE_EVERY_H:
        return
    info = kit_update.check()
    info["checked"] = db.now_iso()
    db.set_meta("update_check", info)
    if info["newer"]:
        notify.update_available(info["latest"])


if __name__ == "__main__":
    sys.exit(main())
