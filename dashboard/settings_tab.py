"""The Settings tab: this channel's answers from first-time setup, an FAQ (dashboard/faq.py), the order of the tabs
along the top (dashboard/tabs.py keeps it), what ReelForge set up on this computer (the hourly stats read, the
reelforge command, the icon), your profiles (deleting one and restoring it: dashboard/service.py profiles_settings),
and the danger zone: factory reset and uninstall (studio/reset.py does both, and neither deletes anything for good).

A mixin of the window's service (dashboard/service.py): the tab calls these, and "settings" is the view it draws. The
tab order is the window's own (it's in what the window starts with, and in an "order" event when another window moves
a tab): the Settings tab moves the tabs there, and set_tab_order keeps the new order.
"""

from __future__ import annotations

from studio.bridge import rpc

from . import config, desktop, faq, tabs
from .view import MUTED, Text

RESTART = 75  # the launcher starts ReelForge again, and does the reset or the uninstall first (studio/reset.py)


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
    who = {"claude": "Claude", "codex": "Codex", "both": "Claude and Codex"}.get(s["ai"]["assistant"], s["ai"]["assistant"])
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
        assistant = ""  # not set up yet: the FAQ covers Claude Code and Codex
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

    def _faq(self, assistant: str, name: str, several: bool) -> list[dict]:
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
        """What ReelForge set up on this computer, each with the button that changes it."""
        from studio import paths as P

        if self.demo:   # made up, like the rest of the demo: everything on
            return [{"key": "stats", "label": "Hourly stats read", "on": True, "button": "Turn off",
                     "value": "on: your stats update every hour, even with ReelForge closed"},
                    {"key": "command", "label": "The reelforge command", "on": True, "button": "Turn off",
                     "value": "on: type reelforge in any terminal"},
                    {"key": "icon", "label": "ReelForge's icon", "on": True, "button": f"Move to the {desktop.BIN}",
                     "value": "there: open ReelForge without typing a command"}]
        left = "left alone in a test copy" if P.test_copy() else "left alone (STUDIO_DRY_SYSTEM)" if P.dry_system() else ""
        out = []
        try:
            from studio import stats_schedule

            state = "off" if left else stats_schedule.status()
        except Exception:
            state = "unsupported"
        out.append({"key": "stats", "label": "Hourly stats read", "on": state == "on",
                    "value": left or {"on": "on: your stats update every hour, even with ReelForge closed",
                                      "off": "off", "other": "on, for another ReelForge folder",
                                      "unsupported": "not available on this computer"}.get(state, state),
                    "button": "" if left or state in ("other", "unsupported") else "Turn off" if state == "on" else "Turn on"})
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
        return out

    @rpc
    def settings_toggle(self, key: str) -> None:
        """A button on the On this computer panel: turn that thing on or off."""
        if self.demo:
            self.notify("Demo mode: nothing is changed.", timeout=4)
            return

        def work() -> None:
            try:
                msg = self._toggle(key)
            except Exception as e:
                msg = f"Couldn't change it: {e}"
            self.loop.call_soon(lambda: (self.notify(msg, timeout=8), self.update_settings()))

        self.loop.run_worker(work, group="settings-toggle")

    @staticmethod
    def _toggle(key: str) -> str:
        if key == "stats":
            from studio import stats_schedule

            return stats_schedule.disable() if stats_schedule.status() == "on" else stats_schedule.enable()
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
