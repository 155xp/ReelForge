"""The Settings tab: this channel's answers from first-time setup (and Copy prompt for your AI, the prompt that starts
your AI on the channel: studio/ai_prompt.py), an FAQ (dashboard/faq.py), the order of the tabs
along the top (dashboard/tabs.py keeps it), what ReelForge set up on this computer (background refresh, which is the
hourly stats read, with its switch; the reelforge command; the icon; ReelForge's own folder, with its Open button
and Move when it isn't in it: studio/move.py) and Restart, your profiles (deleting one and
restoring it: dashboard/service.py profiles_settings), and the danger zone: factory reset and uninstall
(studio/reset.py does both, and neither deletes anything for good).

A mixin of the window's service (dashboard/service.py): the tab calls these, and "settings" is the view it draws. The
tab order is the window's own (it's in what the window starts with, and in an "order" event when another window moves
a tab): the Settings tab moves the tabs there, and set_tab_order keeps the new order.
"""

from __future__ import annotations

import sys

from studio.bridge import rpc

from . import config, desktop, faq, tabs, videos
from .view import MUTED, Text

RESTART = 75  # the launcher starts ReelForge again, doing a reset, an uninstall or a move first if one was asked
              # for (studio/reset.py, studio/move.py)
DEMO_FOLDER = (r"C:\Users\you\ReelForge" if sys.platform == "win32" else "/Users/you/ReelForge"
               if sys.platform == "darwin" else "/home/you/ReelForge")   # where the demo says ReelForge is


def _channel_rows(s: dict) -> list[list[str]]:
    from studio import settings as S

    try:
        from studio.formats import FORMATS

        fmt = FORMATS.get(s["format"]["template"], {}).get("short") or s["format"]["template"]
    except Exception:
        fmt = s["format"]["template"]
    v, c, sched = s["video"], s["captions"], s["schedule"]
    loud = S.LOUDNESS.get(s["sound"]["loudness"], ("", ""))[1].split(",")[0] or f"{s['sound']['target_lufs']} LUFS"
    tags = "no hashtags"
    if c["max_hashtags"]:
        tags = f"up to {c['max_hashtags']} hashtags"
        if c["tiktok_first_tag"]:
            tags += f", #{c['tiktok_first_tag']} first"
        if not c["hashtags_on_x"]:
            tags += ", none on X"
    per = f"{sched['per_day']} a day" if sched["per_day"] else f"{sched['per_week']} a week"
    who = S.ai_names(s["ai"]["assistant"], " and ")
    return [
        ["Channel", s["channel"]["name"]],
        ["Format", f"{fmt}: {s['format']['series']}" if s["format"]["series"] != fmt else fmt],
        ["Videos", f"{v['min_seconds']:g}-{v['max_seconds']:g} s, {v['fps']} fps, {v['style']}"],
        ["Sound", loud],
        ["Captions", tags],
        ["Posting", f"{per}, best at {sched['post_times']}" if sched["post_times"] else per],
        ["Platforms", ", ".join(S.PLATFORM_NAMES.get(p, p) for p in s["platforms"]["enabled"])],
        ["Your AI", who],
    ]


OPEN_FOLDER = f"Open in {desktop.FILES}"   # the folder row's button: the folder itself in Explorer / Finder


def _folder_row(demo: bool) -> dict:
    """Where ReelForge is: in its own folder (green), or somewhere else, with Move... beside its button when it can go
    there (studio/move.py). Its button opens it in Explorer / Finder / the file manager. The demo's is made up."""
    from studio import move
    from studio import paths as P

    if demo:
        return {"key": "folder", "label": "ReelForge's folder", "on": True, "button": OPEN_FOLDER, "move": "",
                "value": DEMO_FOLDER}
    home = move.at_home()
    return {"key": "folder", "label": "ReelForge's folder", "on": home, "value": str(P.ROOT), "button": OPEN_FOLDER,
            "move": "Move…" if not home and not move.problem() else ""}


class SettingsTab:
    """The Settings tab's half of the window's service."""

    def update_settings(self) -> None:
        """The tab's view: its quick parts now, what's on this computer (slower to look up) from a worker."""
        self.emit("settings", self.settings_view(None))
        self.loop.run_worker(self._look_up_computer, group="settings", exclusive=True)

    def _look_up_computer(self) -> None:
        rows = self.computer_rows()
        self.measure_deleted()
        self.loop.call_soon(lambda: self.emit("settings", self.settings_view(rows)))

    def settings_view(self, computer: list[dict] | None) -> dict:
        p = self.profile
        name = p.name if p is not None and not self.demo else "Night Physics" if self.demo else "ReelForge"
        rows: list[list[str]] = []
        onboarded = self.demo or bool(p and p.onboarded)
        assistant: list[str] = []  # not set up yet: the FAQ covers Claude Code and Codex
        try:
            from studio import settings as S

            if onboarded:
                s = S.load() if not self.demo else S.DEFAULTS | {"channel": {**S.DEFAULTS["channel"], "name": name}}
                rows = _channel_rows(s)
                assistant = s["ai"]["assistant"]
        except Exception:
            rows = []
        several = bool(p and not self.demo and self._several())
        return {"name": name, "onboarded": onboarded, "rows": rows, "faq": self._faq(assistant, name, several),
                "computer": computer, "demo": self.demo, "bin": desktop.BIN, "several": several,
                "profiles": self.profiles_settings()}

    def _faq(self, assistant: list[str], name: str, several: bool) -> list[dict]:
        """The FAQ's questions and answers, for this channel (dashboard/faq.py)."""
        from studio import paths as P

        from .service import minutes_setting

        main = self.demo or self.profile is None or self.profile.main
        return faq.items(assistant=assistant, root=P.ROOT, episodes=config.episodes_dir(self.cfg),
                         completed=config.completed_dir(self.cfg), channel=name, main=main, several=several,
                         refresh_minutes=minutes_setting(self.cfg, "refresh_minutes", 30), demo=self.demo)

    @staticmethod
    def _several() -> bool:
        from studio import profiles

        return profiles.several()

    @rpc
    def copy_ai_prompt(self) -> None:
        """Copy prompt for your AI, under this channel's answers: the prompt that starts your AI on this channel
        (studio/ai_prompt.py), the one first-time setup's last screen copies, asking for its next video (its first
        while the Publish tab has none)."""
        if self.demo:
            self.notify("In your own ReelForge, this copies the prompt that starts your AI on your channel.",
                        title="Demo mode", timeout=6)
            return
        from studio import ai_prompt
        from studio import settings as S

        self.copy_text(ai_prompt.text(S.load()["channel"]["name"], self.profile, first=not videos.find(self.cfg)))
        self.notify("Paste it into Claude Code, Codex or any AI that can work with files on this computer.",
                    title="Prompt copied", timeout=8)

    # ---------------------------------------------------------------- the tab order

    def load_tab_order(self) -> None:
        """The order the window starts with: the one kept for every profile, or in the demo the default (nothing the
        demo does is kept)."""
        self.tab_order = tabs.DEFAULT_ORDER if self.demo else tabs.order(config.APP_DIR)

    @rpc
    def set_tab_order(self, order: list | None) -> list[str]:
        """The Settings tab moved a tab (or, with none, put them back in the default order): keep the new order for
        every profile, which every open ReelForge window then shows. Returns it as kept."""
        kept = tabs.tidy(order) if order else tabs.DEFAULT_ORDER
        if self.demo:
            if self.tab_order == tabs.DEFAULT_ORDER and kept != tabs.DEFAULT_ORDER:
                self.notify("Demo mode: this order isn't kept.", timeout=6)
        else:
            try:
                kept = tabs.save_order(kept, config.APP_DIR)
            except OSError as e:
                kept = tabs.order(config.APP_DIR)  # the order that's still kept: the window goes back to it
                self.notify(f"Couldn't change the tab order: {e}", title="Tab order", severity="warning", timeout=10)
                self.emit("order", {"order": list(kept)})
        self.tab_order = kept
        return list(kept)

    def follow_tab_order(self) -> None:
        """Every second: another ReelForge window moved a tab (on any profile), so this one shows the new order too."""
        if self.demo:
            return
        kept = tabs.order(config.APP_DIR)
        if kept != self.tab_order:
            self.tab_order = kept
            self.emit("order", {"order": list(kept)})

    def computer_rows(self) -> list[dict]:
        """What ReelForge set up on this computer, each with the button that changes it. Background refresh (the
        hourly stats read) has a switch instead, where this window can turn it on and off."""
        from studio import paths as P

        if self.demo:   # made up, like the rest of the demo: everything on
            return [{"key": "stats", "label": "Background refresh", "on": True, "switch": True, "button": "",
                     "value": "on: your stats update every hour, even with ReelForge closed"},
                    {"key": "command", "label": "The reelforge command", "on": True, "button": "Turn off",
                     "value": "on: type reelforge in any terminal"},
                    {"key": "icon", "label": "ReelForge's icon", "on": True, "button": f"Move to the {desktop.BIN}",
                     "value": "there: open ReelForge without typing a command"},
                    _folder_row(True)]
        left = "left alone in a test copy" if P.test_copy() else "left alone (STUDIO_DRY_SYSTEM)" if P.dry_system() else ""
        out = []
        try:
            from studio import stats_schedule

            state = "off" if left else stats_schedule.status()
        except Exception:
            state = "unsupported"
        out.append({"key": "stats", "label": "Background refresh", "on": state == "on",
                    "switch": not left and state in ("on", "off"),
                    "value": left or {"on": "on: your stats update every hour, even with ReelForge closed",
                                      "off": "off: your stats update only while ReelForge is open",
                                      "other": "on, for another ReelForge folder",
                                      "unsupported": "not available on this computer"}.get(state, state),
                    "button": ""})
        try:
            from studio import command

            state = "off" if left else command.status()
        except Exception:
            state = "off"
        out.append({"key": "command", "label": "The reelforge command", "on": state == "on",
                    "value": left or ("on: type reelforge in any terminal" if state == "on" else "off"),
                    "button": "" if left else "Turn off" if state == "on" else "Turn on"})
        try:
            from studio import shortcut

            name, what, _ = shortcut.label()
            made = False if left else shortcut.ours()
        except Exception:
            name, what, made = "ReelForge's icon", "", False
        out.append({"key": "icon", "label": name, "on": made,
                    "value": left or (f"there: {what}" if made else "not made"),
                    "button": "" if left else f"Move to the {desktop.BIN}" if made else "Make it"})
        out.append(_folder_row(False))
        return out

    @rpc
    def settings_toggle(self, key: str, on: bool | None = None) -> None:
        """A button or the switch on the On this computer panel: turn that thing on or off (on: which, from the
        switch; None: whichever it isn't). One change at a time, in the order they were asked for."""
        if self.demo:
            self.notify("Demo mode: nothing is changed.", timeout=4)
            return

        def work() -> None:
            with self.toggling:
                try:
                    msg = self._toggle(key, on)
                except Exception as e:
                    msg = f"Couldn't change it: {e}"
            self.loop.call_soon(lambda: (self.notify(msg, timeout=8), self.update_settings()))

        self.loop.run_worker(work, group="settings-toggle")

    @staticmethod
    def _toggle(key: str, on: bool | None = None) -> str:
        if key == "stats":  # background refresh
            from studio import stats_schedule

            if on is None:
                on = stats_schedule.status() != "on"
            return stats_schedule.enable() if on else stats_schedule.disable()
        if key == "command":
            from studio import command

            return command.disable() if command.status() == "on" else command.enable()
        if key == "icon":
            from studio import shortcut

            if shortcut.ours():
                icon = shortcut.path()
                ok = desktop.recycle(icon) and not icon.exists()
                return f"ReelForge's icon is in the {desktop.BIN}." if ok else f"Couldn't move {icon} to the {desktop.BIN}."
            return f"ReelForge's icon is at {shortcut.make()}."
        return f"Nothing called {key!r} to change."

    @rpc
    def open_reelforge_folder(self) -> None:
        """The button beside ReelForge's folder: that folder in Explorer / Finder / the file manager."""
        if self.demo:
            self.notify(f"In your own ReelForge, this opens its folder in {desktop.FILES}.", title="Demo mode",
                        timeout=6)
            return
        from studio import paths as P

        try:
            desktop.open_folder(P.ROOT)
        except OSError as e:
            self.notify(f"Couldn't open {P.ROOT}: {e}", title="ReelForge's folder", severity="warning", timeout=10)

    @rpc
    def restart(self) -> None:
        """Restart, at the bottom of the On this computer panel: the window closes, and the launcher opens ReelForge
        again straight away (on the profile it was on, as after an update). A stats read under way finishes first."""
        self.notify("Restarting ReelForge…", timeout=5)
        self.loop.set_timer(0.5, lambda: self.exit(RESTART, {"restart": True}))

    # ---------------------------------------------------------------- the danger zone

    @rpc
    def reset_info(self) -> dict | None:
        """The Factory reset dialog: what moves into the backup, and the name to type."""
        if self.demo:
            self.notify("Demo mode: nothing is reset.", timeout=4)
            return None
        from studio import paths as P
        from studio import reset

        note = Text()
        note.append("Puts ReelForge back to brand-new", "bold")
        note.append(" and opens first-time setup again. Moved into a backup in ", MUTED)
        note.append("backups", "bold")
        note.append(" (nothing is deleted):\n", MUTED)
        items = reset.reset_items()
        for path, what in items:
            note.append(f"  {P.rel(path)}", "bold")
            note.append(f"  {what}\n", MUTED)
        if not items:
            note.append("  nothing: it's brand-new already\n", MUTED)
        keeps, rest = reset.reset_keeps()
        note.append("\n" + keeps, "bold")
        note.append(rest + " If anything can't be moved, nothing changes. Close any other ReelForge window first.",
                    MUTED)
        return {"note": note.json(), "word": reset.confirm_word()}

    @rpc
    def factory_reset(self, typed: str) -> bool:
        """Asked for with the channel's name typed: ReelForge quits, and the launcher does it as it starts again."""
        from studio import reset

        if self.demo or not reset.matches(typed):
            return False
        reset.request("reset")
        self.notify("Resetting… ReelForge reopens on first-time setup.", title="Factory reset", timeout=5)
        self.loop.set_timer(0.8, lambda: self.exit(RESTART))
        return True

    @rpc
    def uninstall_info(self) -> dict | None:
        """The Uninstall dialog: what goes, where your videos go, and the name to type."""
        if self.demo:
            self.notify("Demo mode: nothing is uninstalled.", timeout=4)
            return None
        from studio import reset

        info = reset.uninstall_info()
        if info["git"]:
            self.notify(f"This ReelForge is a git copy ({info['root']}): delete the folder yourself when you're done "
                        "with it.", title="Not uninstalled", severity="warning", timeout=10)
            return None
        note = Text()
        note.append("Removes ReelForge from this computer.", "bold")
        note.append(f"\n  {info['root']}", "bold")
        note.append(f" goes to the {info['bin']}: the app, Blender, ffmpeg, Bun, its Python, your stats, log-ins and "
                    f"settings. You can put it back from there.\n  {info['system']}", MUTED)
        for f in info["outside"]:
            note.append(f"\n\nVideos outside the ReelForge folder stay where they are: {f}", MUTED)
        return {"note": note.json(), "word": info["word"], "bin": info["bin"], "keep_to": info["keep_to"],
                "videos": info["videos"], "videos_size": info["videos_size"],
                "channels": [c["name"] for c in info["channels"]]}

    @rpc
    def uninstall(self, typed: str, keep: bool) -> bool:
        from studio import reset

        if self.demo or not reset.matches(typed) or reset.git_copy():
            return False
        reset.request("uninstall", keep)
        self.notify("Uninstalling… ReelForge closes now.", title="Uninstall", timeout=5)
        self.loop.set_timer(0.8, lambda: self.exit(RESTART))
        return True

    # ---------------------------------------------------------------- moving ReelForge into its own folder

    @rpc
    def move_info(self) -> dict | None:
        """The Move dialog (studio/move.py): from where to where, what goes along and follows, the Publish tab's
        folders that stay, and why it can't move, if it can't ("problem")."""
        if self.demo:
            self.notify("Demo mode: nothing is moved.", timeout=4)
            return None
        from studio import move

        p = move.plan()
        problem = move.problem(p.target) or ("Another ReelForge window is open: close it first."
                                             if move.others_open(self.window_lock.path if self.window_lock else None)
                                             else "")
        note = Text()
        note.append("Moves ReelForge into a folder of its own", "bold")
        note.append(", the one the install line puts it in:\n", MUTED)
        note.append("  from  ", MUTED)
        note.append(f"{p.source}\n", "bold")
        note.append("  to    ", MUTED)
        note.append(f"{p.target}\n", "bold")
        note.append("\nEverything in it goes along in one step, on the same drive (nothing is copied): your channels, "
                    "stats, log-ins, settings and videos, Blender and the rest.", MUTED)
        follows = move.follows(p.system)
        if follows:
            them = move._and(follows)
            note.append(f" {them[0].upper()}{them[1:]} follow it.", MUTED)
        if p.outside:
            note.append("\n\nThe Publish tab's folders outside ReelForge stay where they are:", MUTED)
            for f in p.outside:
                note.append(f"\n  {f}", MUTED)
        note.append("\n\nReelForge closes, the folder moves" + (" (a small window does it, and waits while anything "
                    "still has a file in it open)" if desktop.WINDOWS else "") + ", and ReelForge opens again from its "
                    "new folder. If you open it in Claude Code or Codex, open the new folder from now on.", MUTED)
        return {"note": note.json(), "to": str(p.target), "problem": problem}

    @rpc
    def move_folder(self, to: str) -> bool:
        """Move ReelForge (asked for in the Move dialog): ReelForge quits, and the launcher starts the move as it
        starts again."""
        from pathlib import Path

        from studio import move

        if self.demo or move.problem(Path(to)):
            return False
        move.request(Path(to))
        self.notify("Moving ReelForge… it opens again from its new folder.", title="Move", timeout=5)
        self.loop.set_timer(0.8, lambda: self.exit(RESTART))
        return True
