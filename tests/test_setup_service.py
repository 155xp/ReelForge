"""The first-run screens' Python side (studio/setup_service.py): the tools list and its downloads, the onboarding
interview step by step (questions that come and go, a format's suggestions, answers that need fixing, the review),
and the bridge the window talks to it through (studio/bridge.py). The screens themselves are tested in
ui/test/setup.test.tsx."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from studio import setup_flow
from studio.bridge import Loop, _plain
from studio.setup_service import Setup

ROOT = Path(__file__).resolve().parent.parent


class Recorder(Loop):
    def __init__(self) -> None:
        super().__init__(out=None)
        self.events: list[tuple[str, object]] = []

    def send(self, msg: dict) -> None:
        msg = json.loads(json.dumps(msg, default=_plain))
        if "ev" in msg:
            self.events.append((msg["ev"], msg["d"]))

    def view(self, name: str):
        return next((d for ev, d in reversed(self.events) if ev == name), None)


def setup(**options) -> tuple[Setup, Recorder]:
    loop = Recorder()
    svc = Setup(loop)
    svc.start({"preview": True, **options})
    return svc, loop


class ToolsTest(unittest.TestCase):
    ITEMS = [
        setup_flow.Item("blender", "Blender 4.5.5", "builds and renders your 3D scenes", False, "about 400 MB", 400),
        setup_flow.Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", True, "ready"),
        setup_flow.Item("fonts", "DejaVu fonts", "the serif font", False, "install them yourself", can_install=False,
                        default=False),
    ]

    def test_the_list_says_what_is_ready_and_what_it_would_set_up(self):
        svc, loop = setup()
        with mock.patch.object(setup_flow, "plan", lambda: list(self.ITEMS)):
            svc.plan()
            self.assertTrue(loop.pump(5, lambda: loop.view("items") is not None))
        items = loop.view("items")
        self.assertEqual([i["key"] for i in items["items"]], ["blender", "ffmpeg", "fonts"])
        self.assertEqual(items["todo"], ["blender"])  # ffmpeg is ready, the fonts need you
        self.assertIn("Let's get ReelForge ready.", "".join(s[0] for s in items["intro"]))

    def test_setting_up_reports_each_job_then_the_health_check(self):
        svc, loop = setup()
        svc.items = list(self.ITEMS)

        def apply(item, progress):
            progress("Downloading Blender", 50_000_000, 100_000_000)
            raise RuntimeError("the network went away")

        with mock.patch.object(setup_flow, "apply", apply), \
                mock.patch.object(setup_flow, "prepare_sounds", lambda progress: None), \
                mock.patch.object(setup_flow.sounds, "missing", lambda: []), \
                mock.patch("studio.tools.find_ffmpeg", lambda: "ffmpeg"):
            svc.run_setup(["blender", "fonts"])  # the fonts can't be set up by ReelForge: left out
            self.assertTrue(loop.pump(60, lambda: (loop.view("checks") or {}).get("rows") is not None))
        self.assertEqual([j["key"] for j in loop.view("jobs")["jobs"]], ["blender", "cache"])
        jobs = [d for ev, d in loop.events if ev == "job"]
        self.assertIn(("blender", "busy", "Downloading Blender  50 of 100 MB"),
                      [(j["key"], j["state"], j["text"]) for j in jobs])
        failed = next(j for j in jobs if j["key"] == "blender" and j["state"] != "busy")
        self.assertEqual((failed["state"], failed["text"]), ("failed", "Didn't work: the network went away"))
        self.assertEqual(next(j for j in reversed(jobs) if j["key"] == "cache")["state"], "ok")
        self.assertTrue(loop.view("checks")["bad"])  # Blender didn't download: Check again shows


class OnboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.svc, self.loop = setup(start="onboard")
        with mock.patch("studio.setup_service.saved_answers", lambda: None):
            self.start = self.svc.onboard_start()

    def fields(self, step: dict) -> dict:
        return {f["key"]: f for f in step["fields"]}

    def test_steps_then_a_review(self):
        self.assertEqual([k for k, _ in self.start["steps"]][-1], "review")
        first = self.svc.onboard_step(0)
        self.assertEqual(first["title"], f"1/{len(self.start['steps'])}  You")
        self.assertEqual(list(self.fields(first)), ["creator", "assistant"])
        self.assertEqual(self.fields(first)["assistant"]["value"], "claude")  # the default, picked

    def test_a_required_answer_holds_the_step(self):
        self.svc.onboard_step(1)
        res = self.svc.onboard_next({"channel_name": "", "about": ""})
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"]["channel_name"], "Please answer this one.")
        self.assertEqual(res["first"], "channel_name")
        res = self.svc.onboard_next({"channel_name": "Night Physics", "about": "What-if videos.", "tone": ["awe"]})
        self.assertTrue(res["ok"])
        self.assertEqual(res["step"]["key"], "format")

    def test_a_new_format_brings_its_suggestions_unless_you_typed_your_own(self):
        step = self.svc.onboard_step(2)
        series = self.fields(step)["series"]["value"]
        changed = self.svc.onboard_change("format", "disaster_pov")
        self.assertNotEqual(self.fields(changed)["series"]["value"], series)
        self.assertTrue(self.fields(changed)["custom_format"]["visible"] is False)
        self.svc.onboard_change("series", "My own series")
        changed = self.svc.onboard_change("format", "doubling")
        self.assertEqual(self.fields(changed)["series"]["value"], "My own series")
        changed = self.svc.onboard_change("format", "custom")
        self.assertTrue(self.fields(changed)["custom_format"]["visible"])  # a custom format asks you to describe it
        self.assertIsNone(self.svc.onboard_change("format", "custom"))  # not a change

    def test_a_custom_length_needs_min_and_max(self):
        self.svc.onboard_step(4)
        self.svc.onboard_change("length", "custom")
        res = self.svc.onboard_next({"length": "custom", "length_custom": "about a minute"})
        self.assertEqual(res["errors"]["length_custom"], "Write it as min-max seconds, e.g. 20-30")
        res = self.svc.onboard_next({"length": "custom", "length_custom": "20-30"})
        self.assertTrue(res["ok"], res)

    def test_back_keeps_what_was_typed(self):
        self.svc.onboard_step(1)
        prev = self.svc.onboard_back({"channel_name": "Half typed"})
        self.assertEqual(prev["key"], "you")
        again = self.svc.onboard_step(1)
        self.assertEqual(self.fields(again)["channel_name"]["value"], "Half typed")

    def test_the_review_lists_every_answer_and_create_writes_nothing_in_preview(self):
        self.svc.answers.update(channel_name="Night Physics", about="What-if videos.")
        review = self.svc.onboard_step(len(self.start["steps"]) - 1)
        self.assertEqual(review["key"], "review")
        self.assertIn("### Your channel", review["review"])
        self.assertIn("**What's your channel called?** Night Physics", review["review"])
        self.assertEqual(self.svc.onboard_create(), {"ok": True})


class BridgeTest(unittest.TestCase):
    """The window's link: lines of JSON in and out, nothing else on stdout, even what a library prints."""

    def test_calls_replies_and_events(self):
        env = dict(os.environ, PYTHONUTF8="1", STUDIO_DRY_SYSTEM="1", REELFORGE_LOG="")
        lines = [{"id": 0, "m": "start", "a": ["setup", {"start": "onboard", "preview": True}]},
                 {"id": 1, "m": "onboard_start", "a": []},
                 {"id": 2, "m": "no_such_call", "a": []},
                 {"id": 3, "m": "stop", "a": []}]
        res = subprocess.run([sys.executable, "-m", "studio.bridge"], cwd=ROOT, env=env, capture_output=True,
                             text=True, encoding="utf-8", timeout=60,
                             input="".join(json.dumps(m) + "\n" for m in lines))
        out = [json.loads(line) for line in res.stdout.splitlines()]  # every line is JSON
        replies = {m["id"]: m for m in out if "id" in m}
        self.assertEqual(replies[0]["r"]["start"], "onboard")
        self.assertIn(["review", "Review"], replies[1]["r"]["steps"])
        self.assertIn("no call named 'no_such_call'", replies[2]["e"])
        self.assertIs(replies[3]["r"], False)  # nothing left to finish
        self.assertEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
