"""Moving ReelForge into a folder of its own (studio/move.py), in a scratch folder laid out like a computer's: the
ReelForge folder on a "Desktop", its own folder waiting in a "home" folder, and video folders outside it. What stops a
move, the Publish tab's outside folders written in full so they name the same places, the rename done at once (macOS,
Linux) or by the small window once ReelForge has closed (Windows: the script itself is run here too), what follows the
folder, a move that never finished, and the window asking for one (the launcher starts it). The Settings tab's row and
dialog are tested in dashboard/tests/test_settings.py and ui/test/settings.test.tsx."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from dashboard import config
from studio import command, generate, move, profiles, reset, terminal_profile
from studio import paths as P

from test_profiles import ANSWERS

KIT = Path(__file__).resolve().parent.parent


class MoveScratch(unittest.TestCase):
    """A ReelForge folder at box/Desktop/ReelForge with Night Physics set up, its own folder to be at
    box/home/ReelForge, and the pipeline's folders outside it at box/rendered. Nothing touches the real computer."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.box = Path(tmp.name).resolve()
        self.root = self.box / "Desktop" / "ReelForge"
        self.home = self.box / "home" / "ReelForge"
        (self.root / "dashboard").mkdir(parents=True)
        self.home.parent.mkdir()
        shutil.copy(KIT / "dashboard" / "config.example.toml", self.root / "dashboard" / "config.example.toml")
        self.point_at(self.root)
        env = mock.patch.dict(os.environ, {"STUDIO_DRY_SYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(profiles.ENV, None)
        for patch in (mock.patch.object(move, "home", lambda: self.home),
                      mock.patch.object(P, "test_copy", lambda: False)):
            patch.start()
            self.addCleanup(patch.stop)
        with redirect_stdout(io.StringIO()):
            generate.write_all(dict(ANSWERS))
        self.write("dashboard/data/stats.db", "stats")
        self.write("dashboard/data/browser/Cookies", "log-in")
        self.write("episodes/ep01_duck/final/ep01_duck.mp4", "video")
        for folder in ("episodes", "completed videos", "renders"):
            (self.box / "rendered" / folder).mkdir(parents=True)

    def point_at(self, root: Path) -> None:
        """Every module's idea of where the ReelForge folder is, as a process started there would have it."""
        for target, name, value in ((profiles, "ROOT", root), (profiles, "FOLDER", root / "profiles"),
                                    (P, "ROOT", root), (P, "DASHBOARD", root / "dashboard"),
                                    (config, "APP_DIR", root / "dashboard"), (move, "ROOT", root),
                                    (reset, "ROOT", root), (reset, "PENDING", root / ".reelforge-pending.json"),
                                    (reset, "BACKUPS", root / "backups")):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, rel: str, text: str, root: Path | None = None) -> Path:
        path = (root or self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def outside_config(self) -> None:
        """The Publish tab reads the pipeline's folders outside ReelForge, written from its dashboard folder."""
        cfg = self.root / "dashboard" / "config.toml"
        text = cfg.read_text(encoding="utf-8")
        text = text.replace('videos_dir = "videos"', 'videos_dir = "../../../rendered/renders"')
        text = text.replace("# episodes_dir", "episodes_dir").replace("# completed_dir", "completed_dir")
        text = text.replace('episodes_dir = "../episodes"', 'episodes_dir = "../../../rendered/episodes"')
        text = text.replace('completed_dir = "../completed videos"',
                            'completed_dir = "../../../rendered/completed videos"')
        cfg.write_text(text, encoding="utf-8")

    def folders(self) -> list[Path]:
        cfg = config.load_config()
        return [config.videos_dir(cfg), config.episodes_dir(cfg), config.completed_dir(cfg)]

    def quiet(self, fn, *args, **kwargs):
        with redirect_stdout(io.StringIO()) as out:
            result = fn(*args, **kwargs)
        self.said = out.getvalue()
        return result


class WhereItGoes(MoveScratch):
    def test_its_own_folder_is_the_one_the_install_line_uses(self):
        with mock.patch.dict(os.environ, {"USERPROFILE": str(self.box / "Users" / "sam")}):
            expected = self.box / "Users" / "sam" / "ReelForge" if P.WINDOWS else Path.home() / "ReelForge"
            self.assertEqual(MOVE_HOME(), expected)   # the real one (the tests' is patched)

    def test_what_stops_a_move(self):
        self.assertEqual(move.problem(), "")
        self.assertIn("already", move.problem(self.root))
        self.assertIn("inside the ReelForge folder", move.problem(self.root / "elsewhere"))
        self.assertIn("is inside", move.problem(self.box / "Desktop"))
        taken = self.write("x.txt", "something", self.home)
        self.assertIn("There's already something", move.problem())
        taken.unlink()
        self.assertEqual(move.problem(), "")   # an empty folder waiting for it is fine
        with mock.patch.object(move, "_drive", lambda path: 2 if move._inside(path, self.home) else 1):
            self.assertIn("another drive", move.problem())
        with mock.patch.object(P, "test_copy", lambda: True):
            self.assertIn("test copy", move.problem())
        (self.root / ".git").mkdir()
        self.assertIn("git copy", move.problem())

    def test_the_folders_outside_it_are_written_in_full_and_still_name_the_same_places(self):
        self.outside_config()
        before = self.folders()
        p = move.plan()
        self.assertEqual(p.target, self.home)
        self.assertEqual(sorted(p.outside), sorted(self.box / "rendered" / f for f in ("renders", "episodes",
                                                                                       "completed videos")))
        self.assertEqual(self.quiet(move.prepare, p), [])
        text = (self.root / "dashboard" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("# where you put finished videos to upload", text)   # its notes stay
        data = tomllib.loads(text)
        self.assertEqual(Path(data["episodes_dir"]), self.box / "rendered" / "episodes")
        self.assertEqual(self.folders(), before)

    def test_folders_inside_it_go_along_and_ones_written_in_full_inside_it_follow_it(self):
        cfg = self.root / "dashboard" / "config.toml"
        text = cfg.read_text(encoding="utf-8").replace("# episodes_dir", "episodes_dir")
        text = text.replace('videos_dir = "videos"', f"videos_dir = {json.dumps(str(self.root / 'clips'))}")
        cfg.write_text(text, encoding="utf-8")
        p = move.plan()
        self.assertEqual(p.outside, [])
        self.assertEqual(p.configs, [(cfg, {"videos_dir": str(self.home / "clips")})])   # ../episodes moves with it

    def test_another_channels_folders_too(self):
        with redirect_stdout(io.StringIO()):
            other = profiles.create("Cool Epic Facts")
            generate.write_all({**ANSWERS, "channel_name": "Cool Epic Facts"}, other)
        cfg = other.config
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("# completed_dir", "completed_dir").replace(
            '"../completed videos"', '"../../../../../rendered/completed videos"'), encoding="utf-8")
        p = move.plan()
        self.assertEqual(p.configs, [(cfg, {"completed_dir": str(self.box / "rendered" / "completed videos")})])

    def test_it_says_what_moves_and_what_stays(self):
        self.outside_config()
        lines = move.summary(move.plan())
        self.assertEqual(lines[1:3], [f"  from  {self.root}", f"  to    {self.home}"])
        self.assertIn(f"  {self.box / 'rendered' / 'episodes'}", lines)
        self.assertEqual(move.follows({"command": True, "stats": True}), ["the reelforge command",
                                                                          "the hourly stats read"])


MOVE_HOME = move.home   # the real one (the tests patch it)


class AtOnce(MoveScratch):
    """macOS and Linux: a running program's folder can be renamed, so it moves at once and --finish runs from the new
    place (here in this process, as the new place's Python would)."""

    def finish_there(self, args, cwd=None, **kw):
        self.assertEqual(args[-2:], ["move", "--finish"])
        self.point_at(self.home)
        self.quiet(move.finish)
        return subprocess.CompletedProcess(args, 0)

    def setUp(self):
        super().setUp()
        self.outside_config()

    def go(self, reopen=False):
        with mock.patch.object(P, "WINDOWS", False), mock.patch.object(move.subprocess, "run", self.finish_there), \
                mock.patch.object(move.os, "execv") as execv, mock.patch.object(move.os, "chdir"):
            code, moved = self.quiet(move.go, move.plan(), reopen=reopen)
        return code, moved, execv

    def test_everything_goes_along_and_the_folders_outside_stay_named(self):
        before = self.folders()
        code, moved, execv = self.go()
        self.assertEqual((code, moved), (0, True))
        self.assertFalse(self.root.exists())
        for rel in ("dashboard/data/stats.db", "dashboard/data/browser/Cookies",
                    "episodes/ep01_duck/final/ep01_duck.mp4", "my-studio/studio.toml", "CLAUDE.md"):
            self.assertTrue((self.home / rel).is_file(), rel)
        self.assertEqual(self.folders(), before)
        self.assertFalse((self.home / move.STATE).exists())   # finished
        self.assertEqual(move.take_marker()["to"], str(self.home))
        self.assertIsNone(move.take_marker())                  # once
        execv.assert_not_called()

    def test_from_the_window_reelforge_opens_again_from_the_new_place(self):
        self.write("bin/reelforge", "#!/bin/sh\n")
        code, moved, execv = self.go(reopen=True)
        self.assertTrue(moved)
        execv.assert_called_once()
        self.assertEqual(execv.call_args.args[1][1:], [str(self.home / "bin" / "reelforge"), "settings"])

    def test_something_in_use_moves_nothing(self):
        with mock.patch.object(P, "WINDOWS", False), mock.patch.object(move.os, "chdir"), \
                mock.patch.object(move, "rename", lambda p, wait=10: "in use"):
            code, moved = self.quiet(move.go, move.plan())
        self.assertEqual((code, moved), (1, False))
        self.assertTrue(self.root.is_dir())
        self.assertFalse((self.root / move.STATE).exists())
        self.assertIn("didn't move (in use)", self.said)


class OnWindows(MoveScratch):
    """Windows: the small window renames the folder once ReelForge has closed."""

    def test_a_small_window_moves_it_once_reelforge_has_closed(self):
        self.outside_config()
        with mock.patch.object(P, "WINDOWS", True), mock.patch.object(move.subprocess, "Popen") as popen:
            code, moved = self.quiet(move.go, move.plan(), reopen=True, pause=False)
        self.assertEqual((code, moved), (0, False))
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("-From") + 1], str(self.root))
        self.assertEqual(args[args.index("-To") + 1], str(self.home))
        self.assertIn("-Open", args)
        self.assertIn("-NoPause", args)
        script = Path(args[args.index("-File") + 1])
        self.addCleanup(lambda: script.unlink(missing_ok=True))
        self.assertIn("[IO.Directory]::Move($From, $To)", script.read_text(encoding="utf-8-sig"))
        self.assertTrue(self.root.is_dir())   # not yet: ReelForge is still running
        state = json.loads((self.root / move.STATE).read_text(encoding="utf-8"))
        self.assertEqual((state["from"], state["to"], state["reopen"]), (str(self.root), str(self.home), True))
        self.assertIn("A small window moves ReelForge", self.said)

    @unittest.skipUnless(sys.platform == "win32", "the small window is PowerShell, on Windows")
    def test_the_small_window_waits_for_the_folder_then_moves_it_and_finishes_from_there(self):
        venv = self.root / ".venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True)
        record = "import json, sys, os; from pathlib import Path\n" \
                 "out = Path(__file__).resolve().parent.parent / 'finished.json'\n" \
                 "out.write_text(json.dumps({'argv': sys.argv[1:], 'prefix': sys.prefix}))\n"
        self.write("bin/reelforge.py", record)
        script = self.box / "move.ps1"
        script.write_text(move.WINDOWS_MOVE, encoding="utf-8-sig")
        busy = (self.root / "dashboard" / "data" / "stats.db").open("rb")   # ReelForge still has it open...
        threading.Timer(3, busy.close).start()                                # ...for three more seconds
        start = time.monotonic()
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-From",
                            str(self.root), "-To", str(self.home), "-NoPause"], capture_output=True, text=True,
                           timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreater(time.monotonic() - start, 2.5)   # it waited for the file to close
        self.assertFalse(self.root.exists())
        done = json.loads((self.home / "finished.json").read_text(encoding="utf-8"))
        self.assertEqual(done["argv"], ["move", "--finish"])
        self.assertEqual(Path(done["prefix"]), self.home / ".venv")   # the .venv works from the new place
        self.assertFalse(script.exists())   # the script tidies itself away

    @unittest.skipUnless(sys.platform == "win32", "the small window is PowerShell, on Windows")
    def test_the_small_window_gives_up_on_a_folder_that_stays_in_use_and_changes_nothing(self):
        script = self.box / "move.ps1"
        quick = move.WINDOWS_MOVE.replace("-lt 600", "-lt 3").replace("Start-Sleep -Seconds 30", "")   # not 10 min
        script.write_text(quick, encoding="utf-8-sig")
        self.write(move.STATE, "{}")
        with (self.root / "dashboard" / "data" / "stats.db").open("rb"):
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-From",
                                str(self.root), "-To", str(self.home), "-NoPause"], capture_output=True, text=True,
                               timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(r.returncode, 1)
        self.assertIn("stayed where it is", r.stdout)
        self.assertTrue((self.root / "dashboard" / "data" / "stats.db").is_file())
        self.assertFalse((self.root / move.STATE).exists())
        self.assertFalse(self.home.exists())


class Finish(MoveScratch):
    def moved(self, system: dict) -> None:
        """As if the folder had just moved here: its note in the new place, and every module looking there."""
        self.write(move.STATE, json.dumps({"from": str(self.root), "to": str(self.home), "system": system,
                                           "asked": "2026-10-30T10:00:00"}))
        os.rename(self.root, self.home)
        self.point_at(self.home)

    def test_what_was_this_folders_follows_it_and_the_next_window_says_so(self):
        self.moved({"command": True, "icon": True, "terminal": False, "stats": True})
        calls = []
        with mock.patch.object(P, "dry_system", lambda: False), \
                mock.patch.object(command, "follow", lambda old: calls.append(("command", old)) or "command ok"), \
                mock.patch("studio.shortcut.make", lambda: calls.append(("icon",)) or "the desktop"), \
                mock.patch.object(terminal_profile, "ensure", lambda: calls.append(("terminal",)) or "wt ok"), \
                mock.patch("studio.stats_schedule.enable", lambda: calls.append(("stats",)) or "stats ok"):
            self.assertEqual(self.quiet(move.finish), 0)
        self.assertEqual(calls, [("command", self.root), ("icon",), ("stats",)])   # not Terminal: it wasn't ours
        self.assertIn(f"ReelForge is in {self.home} now.", self.said)
        self.assertFalse((self.home / move.STATE).exists())
        self.assertEqual(move.take_marker()["problems"], [])

    def test_what_couldnt_follow_it_is_said(self):
        self.moved({"stats": True})

        def broken():
            raise RuntimeError("no scheduler")

        with mock.patch.object(P, "dry_system", lambda: False), mock.patch("studio.stats_schedule.enable", broken):
            self.assertEqual(self.quiet(move.finish), 1)
        self.assertIn("the hourly stats read (no scheduler)", self.said)
        self.assertEqual(move.take_marker()["problems"], ["the hourly stats read (no scheduler)"])

    def test_there_has_to_be_a_move_to_finish(self):
        self.assertEqual(self.quiet(move.finish), 1)
        note = {"from": str(self.root), "to": str(self.home), "asked": "2026-10-30T10:00:00"}
        self.write(move.STATE, json.dumps(note))
        self.assertEqual(self.quiet(move.finish), 1)   # it hasn't moved
        self.assertIn("hasn't moved", self.said)

    def test_one_whose_last_step_never_ran_finishes_when_reelforge_next_starts(self):
        self.moved({})
        self.quiet(move.finish_leftover)
        self.assertFalse((self.home / move.STATE).exists())
        self.assertEqual(move.take_marker()["to"], str(self.home))

    def test_the_note_of_one_that_never_happened_goes_after_a_day(self):
        note = {"from": str(self.root), "to": str(self.home), "asked": "2026-10-30T10:00:00"}
        self.write(move.STATE, json.dumps(note))
        with mock.patch.object(move.time, "time", lambda: time.mktime((2026, 10, 30, 12, 0, 0, 0, 0, -1))):
            move.finish_leftover()
        self.assertTrue((self.root / move.STATE).exists())   # it may still be waiting for ReelForge to close
        with mock.patch.object(move.time, "time", lambda: time.mktime((2026, 11, 1, 12, 0, 0, 0, 0, -1))):
            move.finish_leftover()
        self.assertFalse((self.root / move.STATE).exists())

    def test_a_venv_made_from_a_python_inside_the_folder_follows_it(self):
        self.write(".venv/pyvenv.cfg", f"home = {self.root / 'tools' / 'python' / 'bin'}\n"
                   "include-system-site-packages = false\nversion = 3.13.1\n"
                   f"command = {self.root / 'tools' / 'python' / 'bin' / 'python3'} -m venv {self.root / '.venv'}\n")
        if not P.WINDOWS:
            (self.root / ".venv" / "bin").mkdir()
            (self.root / ".venv" / "bin" / "python").symlink_to(self.root / "tools" / "python" / "bin" / "python3")
            self.write(".venv/bin/pip", f"#!{self.root / '.venv' / 'bin' / 'python'}\nimport pip\n")
        os.rename(self.root, self.home)
        move.repair_venv(self.root, self.home)
        cfg = (self.home / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), cfg)
        self.assertIn(f"home = {self.home / 'tools' / 'python' / 'bin'}", cfg)
        self.assertIn("version = 3.13.1", cfg)
        if not P.WINDOWS:
            self.assertEqual(os.readlink(self.home / ".venv" / "bin" / "python"),
                             str(self.home / "tools" / "python" / "bin" / "python3"))
            self.assertTrue((self.home / ".venv" / "bin" / "pip").read_text().startswith(f"#!{self.home}"))


class FromTheWindow(MoveScratch):
    def test_the_window_asks_and_the_launcher_starts_it(self):
        move.request()
        self.assertEqual(json.loads(reset.PENDING.read_text(encoding="utf-8"))["do"], "move")
        with mock.patch.object(move, "go", return_value=(0, False)) as go:
            self.assertEqual(self.quiet(reset.finish_pending), 0)
        p = go.call_args.args[0]
        self.assertEqual((p.source, p.target), (self.root, self.home))
        self.assertEqual(go.call_args.kwargs, {"reopen": True, "pause": False})
        self.assertFalse(reset.PENDING.exists())   # done once

    def test_nothing_moves_while_another_window_is_open(self):
        lock = profiles.windows(profiles.main()) / "4242.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        take = ("import msvcrt\nmsvcrt.locking(fd, msvcrt.LK_LOCK, 1)" if os.name == "nt" else
                "import fcntl\nfcntl.flock(fd, fcntl.LOCK_EX)")
        holder = subprocess.Popen([sys.executable, "-c", "import os, sys, time\n"
                                   "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)\n" + take +
                                   "\nprint('held', flush=True)\ntime.sleep(30)", str(lock)],
                                  stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")   # another window's, held as a window holds it
        self.assertTrue(move.others_open())
        self.assertFalse(move.others_open(lock))   # unless it's this window's own
        move.request()
        with mock.patch.object(move, "go") as go:
            self.assertEqual(self.quiet(reset.finish_pending), 1)   # no terminal to wait in: it just stops
        go.assert_not_called()
        self.assertIn("Another ReelForge window is open", self.said)

    def test_one_that_couldnt_move_opens_reelforge_again_on_settings_in_a_terminal(self):
        move.request()
        with mock.patch.object(move, "go", return_value=(1, False)), \
                mock.patch.object(reset, "_open_again", return_value=["settings"]):
            self.assertEqual(self.quiet(reset.finish_pending), ["settings"])


class Command(MoveScratch):
    def test_it_asks_first_in_a_terminal_and_says_what_moves(self):
        self.outside_config()
        with mock.patch.object(move, "go") as go:
            self.assertEqual(self.quiet(move.main, []), 2)   # no terminal here, and no --yes
            go.assert_not_called()
            self.assertIn(f"  to    {self.home}", self.said)
            self.assertIn("Run it in a terminal to confirm, or add --yes.", self.said)
            go.return_value = (0, True)
            self.assertEqual(self.quiet(move.main, ["--yes"]), 0)
        self.assertEqual(go.call_args.args[0].target, self.home)
        self.assertEqual(go.call_args.kwargs, {"pause": False})

    def test_somewhere_else_on_the_same_drive(self):
        with mock.patch.object(move, "go", return_value=(0, True)) as go:
            self.assertEqual(self.quiet(move.main, [str(self.box / "Apps" / "ReelForge"), "--yes"]), 0)
        self.assertEqual(go.call_args.args[0].target, self.box / "Apps" / "ReelForge")

    def test_in_its_own_folder_already_there_is_nothing_to_do(self):
        with mock.patch.object(move, "home", lambda: self.root):
            self.assertEqual(self.quiet(move.main, []), 0)
        self.assertIn("in its own folder already", self.said)

    def test_what_stops_it_is_said_and_nothing_changes(self):
        self.write("x.txt", "something", self.home)
        self.assertEqual(self.quiet(move.main, ["--yes"]), 1)
        self.assertIn("There's already something", self.said)
        self.assertEqual(self.quiet(move.main, ["a", "b"]), 2)


class FollowingIt(unittest.TestCase):
    """What follows the folder outside it: the PATH entry (Windows) and Windows Terminal's profile."""

    @unittest.skipUnless(sys.platform == "win32", "Windows paths")
    def test_the_old_folders_path_entry_becomes_the_new_ones_where_it_was(self):
        old = Path(r"C:\Users\sam\Desktop\ReelForge")
        new_bin = str(Path(r"C:\Users\sam\ReelForge") / "bin")
        saved = []
        with mock.patch.object(P, "WINDOWS", True), mock.patch.object(P, "test_copy", lambda: False), \
                mock.patch.object(command, "_dry", lambda: False), mock.patch.object(command, "BIN", Path(new_bin)), \
                mock.patch.object(command, "_win_user_path",
                                  lambda: (r"C:\Tools;C:\Users\sam\Desktop\ReelForge\bin;C:\More", 2)), \
                mock.patch.object(command, "_win_set_user_path", lambda value, kind: saved.append((value, kind))):
            command.follow(old)
        self.assertEqual(saved, [(rf"C:\Tools;{new_bin};C:\More", 2)])

    def test_windows_terminals_profile_is_this_folders_when_it_starts_there(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(terminal_profile, "folder", lambda: Path(tmp)):
            self.assertFalse(terminal_profile.ours())
            frag = Path(tmp) / "ReelForge.json"
            frag.write_text(json.dumps({"profiles": [{"startingDirectory": str(P.ROOT)}]}), encoding="utf-8")
            self.assertTrue(terminal_profile.ours())
            frag.write_text(json.dumps({"profiles": [{"startingDirectory": str(P.ROOT / "other")}]}), encoding="utf-8")
            self.assertFalse(terminal_profile.ours())


if __name__ == "__main__":
    unittest.main()
