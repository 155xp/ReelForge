"""reelforge [1-6 | a tab's name | notifications | refresh] [--demo]      (also: python -m dashboard ...)

  reelforge                ReelForge on the Overview tab
  reelforge 4              straight to a tab: 1 Overview, 2 Videos, 3 Compare, 4 Publish, 5 Accounts, 6 Updates
  reelforge publish        the same, by name
  reelforge notifications  with the notifications drawer open
  reelforge refresh        read every platform's stats once, save them and exit (the hourly background job)
  reelforge --demo         try it on made-up data; nothing is read or saved

Exit codes: 0 fine, 2 a word it doesn't know, 3 the kit's Python packages are missing (run setup), 75 ReelForge
updated itself and the launcher should start it again.
"""

from __future__ import annotations

import argparse
import sys
import threading
from datetime import datetime

try:
    import httpx  # noqa: F401
except ImportError:
    sys.exit(3)  # the launchers take exit code 3 to mean "repair the environment"

from . import config, db, notify, sync  # noqa: E402

TAB_IDS = ("overview", "videos", "compare", "publish", "accounts", "updates")
TABS: dict[str, str] = {
    **{str(i): tab for i, tab in enumerate(TAB_IDS, 1)},
    **{tab: tab for tab in TAB_IDS},
    "home": "overview", "video": "videos", "post": "publish", "posts": "publish",
    "upload": "publish", "uploads": "publish", "account": "accounts", "login": "accounts", "logins": "accounts",
    "update": "updates", "notifications": "overview", "notification": "overview", "alerts": "overview",
}
DRAWER_WORDS = {"notifications", "notification", "alerts"}
USAGE = ("reelforge [1-6 | overview | videos | compare | publish | accounts | updates | notifications | refresh] "
         "[--demo]")


def tab_for(word: str) -> str | None:
    """The tab a word opens ("4", "publish", "post" -> "publish"), or None if it isn't one."""
    return TABS.get((word or "").strip().lower())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reelforge", usage=USAGE,
                                     description="ReelForge: your stats on TikTok, YouTube, Instagram and X, the "
                                                 "Publish tab, notifications and updates.")
    parser.add_argument("--demo", action="store_true", help="try ReelForge on made-up data; nothing is read or saved")
    parser.add_argument("what", nargs="?", default="", help="a tab (1-6 or its name), notifications, or refresh")
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

    if word == "refresh":
        cfg, platforms = load_platforms(args.demo)
        return refresh(platforms, cfg, demo=args.demo)

    # The window is the OpenTUI app in ui/; it runs dashboard/service.py through studio/bridge.py.
    from studio import tui, ui

    tui.set_title("ReelForge TEST" if (config.APP_DIR.parent / "TEST-COPY.txt").exists() else "ReelForge")
    if sys.platform == "win32":
        threading.Thread(target=_terminal_profile, daemon=True).start()
    code, _ = ui.run("dashboard", {"tab": tab_for(word) or "overview", "drawer": word in DRAWER_WORDS,
                                   "demo": args.demo})
    if code == 75:
        print("ReelForge updated itself; starting it again…")
    return code


def load_platforms(demo: bool = False, only_demos: bool = False) -> tuple[dict, dict]:
    """The settings and the platforms to show, with the stats database open: the real one, or for the demo a fresh
    one of made-up stats (only_demos: the Publish tab lists just the kit's own demo videos, for the README's
    pictures)."""
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
        return cfg, demo_data.platforms()
    from .platforms import build

    db.init(config.DB_PATH)
    # Only the platforms you've put a handle in; with none yet, all four, so the Accounts tab shows the way.
    every = build(cfg)
    return cfg, {k: p for k, p in every.items() if p.public_handle} or every


def _terminal_profile() -> None:
    """The anvil on ReelForge's tab in Windows Terminal (studio/terminal_profile.py), checked in the background each
    time ReelForge opens: a nicety, never a reason not to open."""
    try:
        from studio import terminal_profile

        terminal_profile.ensure()
    except Exception:
        pass


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
