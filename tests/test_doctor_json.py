"""Doctor's JSON output, exit codes, and render progress without installing tools."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from studio import KIT_NAME, KIT_VERSION, doctor
from studio import paths as P
from studio.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = "        building the example scene in Blender (about a minute)...\n"


def checks_for(rows):
    def checks(render_test=False, quiet=False):
        report = doctor.Report(quiet)
        for row in rows:
            report.add(*row)
        if render_test and not report.failed:
            doctor.render_check(report)
        return report
    return checks


class DoctorJson(unittest.TestCase):
    def test_json_contains_the_report_and_preserves_exit_codes(self):
        for status, code in ((doctor.OK, 0), (doctor.WARN, 0), (doctor.FAIL, 1)):
            with self.subTest(status=status):
                rows = [(doctor.OK, "Python", ""), (status, 'A "check"', 'Café\\tools\ntry "setup"')]
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(doctor, "checks", checks_for(rows)), \
                        redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(doctor.run(json_output=True), code)
                self.assertEqual(json.loads(out.getvalue()), {
                    "version": KIT_VERSION,
                    "root": str(P.ROOT),
                    "failed": status == doctor.FAIL,
                    "checks": [{"status": doctor.OK, "what": "Python", "detail": ""},
                               {"status": status, "what": 'A "check"', "detail": 'Café\\tools\ntry "setup"'}],
                })
                self.assertEqual(err.getvalue(), "")

    def test_default_text_and_exit_codes_are_unchanged(self):
        for status, mark, summary, code in (
            (doctor.OK, "  ok  ", "All set.", 0),
            (doctor.WARN, " warn ", "Ready, with the warnings above.", 0),
            (doctor.FAIL, " FAIL ", "Some checks FAILED. Fix those first (the line says how), then run this again.", 1),
        ):
            with self.subTest(status=status):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(doctor, "checks", checks_for([(status, "Python", "3.12")])), \
                        redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(doctor.run(), code)
                self.assertEqual(out.getvalue(), f"{KIT_NAME} {KIT_VERSION}: checking {P.ROOT}\n\n"
                                 f"[{mark}] Python: 3.12\n\n{summary}\n")
                self.assertEqual(err.getvalue(), "")

    def test_render_progress_uses_stderr_only_in_json_mode(self):
        for json_output in (True, False):
            for render_ok in (True, False):
                with self.subTest(json_output=json_output, render_ok=render_ok), \
                        tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    example = root / "examples" / "demo_doubling_duck" / "episode.json"
                    example.parent.mkdir(parents=True)
                    example.write_text("{}", encoding="utf-8")
                    (root / "episodes").mkdir()

                    def render(cmd, **kwargs):
                        if render_ok:
                            still = Path(cmd[2]) / "build" / "stills" / "s_0021.jpg"
                            still.parent.mkdir(parents=True)
                            still.write_bytes(b"x" * 10_001)
                        return subprocess.CompletedProcess(cmd, 0 if render_ok else 1,
                                                           stdout='Blender: "scene" failed\nDetails: café', stderr="")

                    out, err = io.StringIO(), io.StringIO()
                    args = ["doctor", "--render-test", *(["--json"] if json_output else [])]
                    with mock.patch.object(P, "ROOT", root), \
                            mock.patch.object(P, "EXAMPLES", root / "examples"), \
                            mock.patch("studio.reset.finish_pending", return_value=None), \
                            mock.patch.object(doctor, "checks", checks_for([(doctor.OK, "Python", "ready")])), \
                            mock.patch.object(doctor.subprocess, "run", side_effect=render), \
                            redirect_stdout(out), redirect_stderr(err):
                        self.assertEqual(main(args), 0 if render_ok else 1)
                    if json_output:
                        data = json.loads(out.getvalue())
                        self.assertIs(data["failed"], not render_ok)
                        check = data["checks"][-1]
                        self.assertEqual(check["what"], "Render test")
                        self.assertEqual(check["status"], doctor.OK if render_ok else doctor.FAIL)
                        if not render_ok:
                            self.assertIn('Blender: "scene" failed\nDetails: café', check["detail"])
                        self.assertEqual(err.getvalue(), PROGRESS)
                    else:
                        self.assertIn(PROGRESS, out.getvalue())
                        self.assertIn("Render test:", out.getvalue())
                        self.assertEqual(err.getvalue(), "")
                    self.assertEqual(list((root / "episodes").iterdir()), [])
                    self.assertEqual((root / "my-studio" / "render-test.jpg").exists(), render_ok)

    def test_cli_stdout_is_json_when_tools_are_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "REELFORGE_PROFILE": ".", "STUDIO_ONLY_KIT_TOOLS": "1",
                   "STUDIO_BLENDER": str(Path(folder) / "missing-blender"),
                   "STUDIO_FFMPEG": str(Path(folder) / "missing-ffmpeg")}
            for flags in (("--json",), ("--render-test", "--json")):
                with self.subTest(flags=flags):
                    result = subprocess.run([sys.executable, "-m", "studio", "doctor", *flags], cwd=ROOT, env=env,
                                            capture_output=True, text=True, encoding="utf-8", timeout=60)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["version"], KIT_VERSION)
                    self.assertEqual(data["root"], str(ROOT))
                    self.assertIs(data["failed"], True)
                    statuses = {check["what"]: check["status"] for check in data["checks"]}
                    self.assertEqual(statuses["Blender"], doctor.FAIL)
                    self.assertEqual(statuses["ffmpeg"], doctor.FAIL)
                    self.assertNotIn("Render test", statuses)
