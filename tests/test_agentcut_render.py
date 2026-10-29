"""Real headless editor -> post -> QA -> manual Publish handoff (opt-in; CI runs it).

Install the optional editor first, then REELFORGE_AGENTCUT_RENDER_TEST=1 python -m unittest
discover -s tests -p test_agentcut_render.py -v. No account, GPU or visible window needed.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get("REELFORGE_AGENTCUT_RENDER_TEST") == "1", "optional headless render test")
class HeadlessDelivery(unittest.TestCase):
    def run_command(self, *args, ok=True):
        result = subprocess.run([sys.executable, *map(str, args)], cwd=KIT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=240)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_footage_edit_passes_real_qa_and_reaches_publish_only_after_review(self):
        from studio import agentcut, tools

        ffmpeg = tools.find_ffmpeg()
        self.assertTrue(ffmpeg, "ffmpeg is required")
        agentcut.executable()
        folder = KIT / "profiles"
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="agentcut-test-", dir=folder) as tmp:
            profile = Path(tmp)
            (profile / "profile.toml").write_text('name = "AgentCut acceptance test"\n', encoding="utf-8")
            (profile / "my-studio").mkdir()
            (profile / "my-studio" / "studio.toml").write_text(
                '[video]\nbackend = "agentcut"\nmin_seconds = 3\nmax_seconds = 3\n', encoding="utf-8")
            self.run_command("-m", "studio", "-p", profile.name, "agentcut", "new", "test", "--topic", "Test fixture")
            ep = profile / "episodes" / "ep01_test"
            spec = json.loads((ep / "episode.json").read_text())
            spec.update(title="Headless editing test", title_card={"start": 0, "end": 1.5, "scrim": 0.5})
            (ep / "episode.json").write_text(json.dumps(spec), encoding="utf-8")
            media = ep / "edit" / "media" / "source.mp4"
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=360x640:rate=30:duration=4", "-f", "lavfi", "-i",
                            "sine=frequency=220:sample_rate=48000:duration=4", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(media)], check=True)
            html = '''<!doctype html><html><head><meta charset="utf-8"><title>Test fixture</title>
<script src="lib/gsap.min.js"></script><style>
html,body{margin:0;width:1080px;height:1920px;background:#14243d;overflow:hidden}
video{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}
</style></head><body><div id="main" data-composition-id="main" data-width="1080" data-height="1920"
 data-fps="30" data-start="0" data-duration="3">
<video id="first" class="clip" src="media/source.mp4" data-start="0" data-duration="1.5"
 data-media-start="0" data-track-index="0" data-has-audio="true" playsinline></video>
<video id="second" class="clip" src="media/source.mp4" data-start="1.5" data-duration="1.5"
 data-media-start="2" data-track-index="0" data-has-audio="true" playsinline></video>
</div><script>const tl=gsap.timeline({paused:true});tl.to({}, {duration:3});
window.__timelines={main:tl};</script></body></html>'''
            (ep / "edit" / "index.html").write_text(html, encoding="utf-8")
            # No Blender is installed or selected. A bogus override proves this path never launches it.
            env_before = os.environ.get("STUDIO_BLENDER")
            os.environ["STUDIO_BLENDER"] = str(profile / "no-blender")
            try:
                self.run_command("-m", "studio", "agentcut", "validate", ep)
                self.run_command("-m", "studio", "agentcut", "render", ep)
                self.assertEqual(len(list((ep / "build" / "frames").glob("f_*.jpg"))), 90)
                self.assertTrue((ep / "build" / "stills" / "s_0001.jpg").is_file())
                self.run_command("pipeline/make_episode.py", ep, "--steps", "post")
                report = json.loads((ep / "build" / "qa" / "qa.json").read_text())
                self.assertTrue(report["pass"], report)
                self.assertFalse((ep / "build" / "qa" / "review.md").exists())
                blocked = self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver", ok=False)
                self.assertIn("review", blocked.stdout + blocked.stderr)
                # This is a synthetic test fixture, not a production video's creative approval.
                (ep / "build" / "qa" / "review.md").write_text(
                    "Automated fixture: generated motion and tone, exact 90-frame render, full QA passed.\nAPPROVED\n")
                shipped = self.run_command("pipeline/make_episode.py", ep, "--steps", "ship")
                self.assertIn("READY in ReelForge", shipped.stdout)
                copies = list((profile / "completed videos").glob("*/*.mp4"))
                self.assertEqual(len(copies), 1)
                final = ep / "final" / "ep01_test.mp4"
                self.assertEqual(hashlib.sha256(final.read_bytes()).digest(), hashlib.sha256(copies[0].read_bytes()).digest())
                # A changed composition cannot silently reuse the old picture/audio pair.
                (ep / "edit" / "index.html").write_text(html.replace("#14243d", "#223344"), encoding="utf-8")
                stale = self.run_command("pipeline/make_episode.py", ep, "--steps", "post", ok=False)
                self.assertIn("changed", stale.stdout + stale.stderr)
            finally:
                if env_before is None:
                    os.environ.pop("STUDIO_BLENDER", None)
                else:
                    os.environ["STUDIO_BLENDER"] = env_before


if __name__ == "__main__":
    unittest.main()
