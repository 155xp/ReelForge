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
from datetime import datetime

try:
    import httpx  # noqa: F401
    import textual  # noqa: F401
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
    if args.demo:
        from . import demo

        path = config.DATA_DIR / "demo.db"
        for suffix in ("", "-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        db.init(path)
        demo.seed(video=demo.newest_video(cfg))
        platforms = demo.platforms()
    else:
        from .platforms import build

        db.init(config.DB_PATH)
        # Only the platforms you've put a handle in; with none yet, all four, so the Accounts tab shows the way.
        every = build(cfg)
        platforms = {k: p for k, p in every.items() if p.public_handle} or every

    if word == "refresh":
        return refresh(platforms, cfg, demo=args.demo)

    from .app import ReelForge

    app = ReelForge(cfg, platforms, demo=args.demo, tab=tab_for(word) or "overview", drawer=word in DRAWER_WORDS)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(app.title)  # the terminal tab's name
        try:  # the anvil on ReelForge's tab in Windows Terminal (studio/terminal_profile.py)
            from studio import terminal_profile

            terminal_profile.ensure()
        except Exception:
            pass  # a nicety: never a reason not to open
    app.run()
    import threading

    if any(t.is_alive() and not t.daemon for t in threading.enumerate() if t is not threading.main_thread()):
        print("Finishing the stats read that was running (it closes its browser first)…")
    code = app.return_code or 0
    if code == 75:
        print("ReelForge updated itself; starting it again…")
    return code


def refresh(platforms: dict, cfg: dict, demo: bool = False) -> int:
    """One stats read, then new videos and (every few hours) the update check, all saved for the next look."""
    done, errors = sync.refresh(platforms, cfg, manual=True)
    db.compact()
    if not demo:
        for extra in (lambda: notify.check_videos(cfg), _check_updates):
            try:
                extra()
            except Exception:
                pass  # extras: a hiccup here never fails the read
    lines = ["refreshed: " + (", ".join(done) or "nothing due"), *("error: " + e for e in errors)]
    print("\n".join(lines))
    # A scheduled refresh has no window to read, so it also keeps a short log.
    log = config.DATA_DIR / "refresh.log"
    try:
        old = log.read_text("utf-8").splitlines()[-200:] if log.exists() else []
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        log.write_text("\n".join([*old, *(f"{stamp}  {line}" for line in lines)]) + "\n", "utf-8")
    except OSError:
        pass
    return 1 if errors else 0


def _check_updates() -> None:
    """Ask GitHub about a newer ReelForge at most every 6 hours, so the bell can say so before you open the app."""
    from .app import UPDATE_EVERY_H, _hours_since

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
