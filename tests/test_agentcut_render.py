"""Real 62-second editor -> post -> QA -> manual Publish acceptance (CI opts in).

Install AgentCut, then set REELFORGE_AGENTCUT_RENDER_TEST=1 and run unittest discover
-s tests -p test_agentcut_render.py -v. The same test must pass natively on Intel and
Apple Silicon macOS; a Linux result is supplemental. No accounts or uploads are used.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parent.parent
FPS, SECONDS, SAMPLE_RATE = 30, 62, 48000
HALF = SECONDS // 2
CUT_FRAME = HALF * FPS


@unittest.skipUnless(os.environ.get("REELFORGE_AGENTCUT_RENDER_TEST") == "1", "optional headless render test")
class HeadlessDelivery(unittest.TestCase):
    def setUp(self):
        self.artifacts = KIT / "dist" / "agentcut-acceptance" / f"{platform.system()}-{platform.machine()}"
        if self.artifacts.exists():
            shutil.rmtree(self.artifacts)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / "commands.txt").write_text("", encoding="utf-8")

    def run_command(self, *args, ok=True):
        result = subprocess.run([sys.executable, *map(str, args)], cwd=KIT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=1800)
        with (self.artifacts / "commands.txt").open("a", encoding="utf-8") as log:
            log.write(f"{args!r}\nexit={result.returncode}\n{result.stdout}\n{result.stderr}\n")
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def probe(self, path):
        result = subprocess.run([self.ffprobe, "-v", "error", "-count_frames", "-show_streams",
                                 "-show_format", "-of", "json", str(path)], check=True,
                                capture_output=True, text=True, timeout=120)
        return json.loads(result.stdout)

    def frame(self, path, index):
        import numpy as np
        result = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(path), "-vf",
                                 f"select=eq(n\\,{index}),scale=360:640", "-frames:v", "1",
                                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True,
                                capture_output=True, timeout=120)
        self.assertEqual(len(result.stdout), 360 * 640 * 3)
        return np.frombuffer(result.stdout, np.uint8).reshape(640, 360, 3).astype(float)

    def audio(self, path):
        import numpy as np
        result = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ar",
                                 str(SAMPLE_RATE), "-ac", "2", "-f", "f32le", "-"], check=True,
                                capture_output=True, timeout=120)
        return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2)

    def assert_audio_transition(self, samples, at, before, after):
        """Find a frequency change independently of metadata and require sync within 50 ms."""
        import numpy as np
        mono = samples.mean(axis=1)
        length = round(0.04 * SAMPLE_RATE)
        t = np.arange(length) / SAMPLE_RATE
        basis = [np.exp(-2j * np.pi * freq * t) * np.hanning(length) for freq in (before, after)]
        centers = np.arange(at - 0.15, at + 0.151, 0.01)
        changed = []
        for center in centers:
            start = round(center * SAMPLE_RATE) - length // 2
            segment = mono[start:start + length]
            power = [abs(np.dot(segment, b)) for b in basis]
            changed.append(power[1] > power[0])
        self.assertFalse(changed[0], (at, before, after))
        self.assertTrue(changed[-1], (at, before, after))
        measured = float(centers[next(i for i, value in enumerate(changed) if value)])
        self.assertLessEqual(abs(measured - at), 0.05, f"audio transition {measured:.3f}s, picture {at}s")
        return measured

    def make_source(self, path, tone, change, hue):
        # Continuous motion detects frozen/duplicated frames. The source changes tone and
        # a visual marker together, so seeking the picture without seeking audio fails.
        video_filter = (f"testsrc2=size=360x640:rate={FPS}:duration={HALF + 3},hue=h={hue},"
                        f"drawbox=x=0:y=0:w=80:h=80:color=yellow:t=fill:enable='gte(t,{change})'")
        audio_filter = (f"aevalsrc=0.12*sin(2*PI*if(lt(t\\,{change})\\,{tone}\\,{tone * 2})*t)"
                        f":s={SAMPLE_RATE}:d={HALF + 3}")
        subprocess.run([self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", video_filter,
                        "-f", "lavfi", "-i", audio_filter, "-c:v", "libx264", "-crf", "16",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(path)],
                       check=True, timeout=120)

    def approve_fixture(self, ep):
        report = json.loads((ep / "build" / "qa" / "qa.json").read_text())
        self.assertTrue(report["pass"], report)
        (ep / "build" / "qa" / "review.md").write_text(
            "Synthetic acceptance fixture only: checked trimmed pictures, cut timing, local font, "
            "overlays, captions, audio sync, loudness and passing final-file QA.\n"
            f"Review-SHA256: {report['review_fingerprint']}\nAPPROVED\n", encoding="utf-8")
        return report

    def test_footage_edit_passes_real_qa_and_reaches_publish_only_after_review(self):
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        from studio import agentcut, tools

        self.ffmpeg = tools.find_ffmpeg()
        self.assertTrue(self.ffmpeg, "ffmpeg is required")
        self.ffprobe = tools.ffprobe_for(self.ffmpeg)
        agentcut.executable()
        node = agentcut.runtime()
        node_arch = subprocess.run([node, "-p", "process.arch"], capture_output=True, text=True,
                                   check=True, timeout=30).stdout.strip()
        if platform.system() == "Darwin":
            self.assertEqual(node_arch, {"arm64": "arm64", "x86_64": "x64"}[platform.machine()],
                             "Node must run natively, not through architecture emulation")
        print(f"Native acceptance: {platform.system()} {platform.machine()}, Node {node_arch}", flush=True)
        folder = KIT / "profiles"
        folder.mkdir(exist_ok=True)
        # Spaces occur in the profile/episode absolute path, both media paths, and font URL.
        with tempfile.TemporaryDirectory(prefix="AgentCut acceptance ", dir=folder) as tmp:
            profile = Path(tmp)
            (profile / "profile.toml").write_text('name = "AgentCut acceptance test"\n', encoding="utf-8")
            (profile / "my-studio").mkdir()
            (profile / "my-studio" / "studio.toml").write_text(
                f'[video]\nbackend = "agentcut"\nmin_seconds = {SECONDS}\nmax_seconds = {SECONDS}\n', encoding="utf-8")
            self.run_command("-m", "studio", "-p", profile.name, "agentcut", "new", "test", "--topic", "Test fixture")
            ep = profile / "episodes" / "ep01_test"
            spec_file = ep / "episode.json"
            spec = json.loads(spec_file.read_text())
            spec.update(title="Native footage acceptance", title_card={"start": 0, "end": 2, "scrim": 0.5},
                        lines=[[6, 9, "The first trimmed clip"], [HALF + 6, HALF + 9, "The second trimmed clip"]],
                        cover={"time": 6, "kicker": "NATIVE", "keyword": "EDIT", "tail": "Acceptance"})
            spec_file.write_text(json.dumps(spec), encoding="utf-8")
            media = ep / "edit" / "media"
            sources = [media / "first source.mp4", media / "second source.mp4"]
            self.make_source(sources[0], 440, 5, 0)
            self.make_source(sources[1], 660, 7, 90)
            # The bundled mono font has stable metrics on both Mac architectures; loading
            # this local URL also exercises fonts outside system font discovery.
            font_source = tools.find_fonts()[3]
            self.assertTrue(font_source.is_file(), font_source)
            shutil.copyfile(font_source, media / "local font.ttf")
            badge = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
            ImageDraw.Draw(badge).ellipse((0, 0, 99, 99), fill=(255, 0, 255, 255))
            badge.save(media / "overlay badge.png")
            html = '''<!doctype html><html><head><meta charset="utf-8"><title>Native acceptance</title>
<script src="lib/gsap.min.js"></script><style>
@font-face{font-family:FixtureFont;src:url('media/local%20font.ttf')}
html,body{margin:0;width:1080px;height:1920px;background:#14243d;overflow:hidden}
#main{position:relative;width:1080px;height:1920px}
video{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}
#font{position:absolute;left:60px;top:1680px;width:960px;height:140px;background:black;color:white;
font-family:FixtureFont,monospace;font-size:80px;line-height:120px;white-space:nowrap}
#badge{position:absolute;left:900px;top:1500px;width:100px;height:100px}
</style></head><body><div id="main" data-composition-id="main" data-width="1080" data-height="1920"
 data-fps="30" data-start="0" data-duration="__SECONDS__">
<video id="first" class="clip" src="media/first%20source.mp4" data-start="0" data-duration="__HALF__"
 data-media-start="1" data-track-index="0" data-has-audio="true" playsinline></video>
<video id="second" class="clip" src="media/second%20source.mp4" data-start="__HALF__" data-duration="__HALF__"
 data-media-start="2" data-track-index="0" data-has-audio="true" playsinline></video>
<div id="font" class="clip" data-start="0" data-duration="__SECONDS__" data-track-index="1">LOCAL FONT</div>
<img id="badge" class="clip" src="media/overlay%20badge.png" data-start="0" data-duration="__SECONDS__" data-track-index="2">
</div><script>const tl=gsap.timeline({paused:true});tl.to({}, {duration:__SECONDS__});
window.__timelines={main:tl};</script></body></html>'''.replace('__SECONDS__', str(SECONDS)).replace('__HALF__', str(HALF))
            (ep / "edit" / "index.html").write_text(html, encoding="utf-8")
            env_before = os.environ.get("STUDIO_BLENDER")
            os.environ["STUDIO_BLENDER"] = str(profile / "no Blender installed")
            try:
                self.run_command("-m", "studio", "agentcut", "validate", ep)
                self.run_command("-m", "studio", "agentcut", "render", ep)
                frames = ep / "build" / "frames"
                self.assertEqual(sorted(p.name for p in frames.iterdir()),
                                 [f"f_{n:04d}.jpg" for n in range(1, FPS * SECONDS + 1)])
                self.assertTrue((ep / "build" / "stills" / "s_0001.jpg").is_file())
                rendered = ep / "build" / "agentcut.mp4"
                # Compare source pictures at the chosen trim offsets, including both sides
                # of the cut. Ignore the lower region containing the deliberate HTML overlay.
                for index, source, source_index in ((0, sources[0], 30), (119, sources[0], 149),
                                                     (120, sources[0], 150), (CUT_FRAME - 1, sources[0], CUT_FRAME + FPS - 1),
                                                     (CUT_FRAME, sources[1], 2 * FPS), (CUT_FRAME + 5 * FPS, sources[1], 7 * FPS),
                                                     (SECONDS * FPS - 1, sources[1], (HALF + 2) * FPS - 1)):
                    actual = self.frame(rendered, index)[:450]
                    expected = self.frame(source, source_index)[:450]
                    self.assertLess(float(np.abs(actual - expected).mean()), 9.0,
                                    f"render frame {index} does not match source frame {source_index}")
                sample = self.frame(rendered, 300)
                self.assertGreater(float(sample[505:528, 305:329, 0].mean()), 200)
                self.assertGreater(float(sample[505:528, 305:329, 2].mean()), 200)
                # The text width must match the actual font's metrics (fallback monospace
                # gives a different width); bright glyphs must be present over the black card.
                text_pixels = sample[560:607, 20:340].min(axis=2) > 200
                cols = np.where(text_pixels.any(axis=0))[0]
                self.assertGreater(len(cols), 60, "local font text did not render")
                font = ImageFont.truetype(str(font_source), 80)
                # Compare glyph silhouettes with the supplied font, so rendering a system
                # fallback with similar monospace metrics does not accidentally pass.
                expected_text = Image.new("L", (960, 140))
                ImageDraw.Draw(expected_text).text((0, 0), "LOCAL FONT", font=font, fill=255, anchor="lt")
                expected_text = expected_text.crop(expected_text.getbbox())
                self.assertAlmostEqual(int(cols[-1] - cols[0] + 1) * 3, expected_text.width, delta=12)
                with Image.open(frames / "f_0301.jpg") as image:
                    actual_text = np.asarray(image.convert("RGB").crop((60, 1680, 1020, 1820))).min(axis=2) > 200
                yy, xx = np.where(actual_text)
                actual_text = actual_text[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
                reference_text = np.asarray(expected_text.resize((actual_text.shape[1], actual_text.shape[0]))) > 200
                self.assertGreater(float((actual_text & reference_text).sum() / (actual_text | reference_text).sum()),
                                   0.70, "rendered glyphs do not match the supplied local font")
                self.run_command("pipeline/make_episode.py", ep, "--steps", "post")
                report = json.loads((ep / "build" / "qa" / "qa.json").read_text())
                self.assertTrue(report["pass"], report)
                checks = {c["check"]: c for c in report["checks"]}
                for check in ("video stream", "audio stream", "duration", "frame count",
                              "audio length matches video", "loudness (LUFS)", "loudest moment", "true peak"):
                    self.assertEqual(checks[check]["status"], "PASS", checks[check])
                final = ep / "final" / "ep01_test.mp4"
                info = self.probe(final)
                video = next(s for s in info["streams"] if s["codec_type"] == "video")
                self.assertEqual((video["width"], video["height"]), (1080, 1920))
                self.assertEqual(int(video["nb_read_frames"]), FPS * SECONDS)
                self.assertAlmostEqual(float(info["format"]["duration"]), SECONDS, delta=0.1)
                for index, source, source_index in ((CUT_FRAME - 1, sources[0], CUT_FRAME + FPS - 1), (CUT_FRAME, sources[1], 2 * FPS)):
                    self.assertLess(float(np.abs(self.frame(final, index)[:450] -
                                                 self.frame(source, source_index)[:450]).mean()), 9.0,
                                    f"final output cut is incorrect at frame {index}")
                audio = self.audio(final)
                measured = [self.assert_audio_transition(audio, *transition)
                            for transition in ((4, 440, 880), (HALF, 880, 660), (HALF + 5, 660, 1320))]
                # Post-production title/story overlays must change visible pixels.
                for frame_index, region in ((30, (slice(70, 230), slice(20, 340))),
                                            (210, (slice(280, 500), slice(20, 340)))):
                    delta = np.abs(self.frame(final, frame_index)[region] - self.frame(rendered, frame_index)[region])
                    self.assertGreater(float(delta.mean()), 1.0, "post overlay missing")
                self.assertTrue((ep / "final" / "cover.jpg").stat().st_size > 1000)
                self.assertIn(spec["title"], (ep / "final" / "caption.txt").read_text())
                self.assertFalse((ep / "build" / "qa" / "review.md").exists())
                blocked = self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver", ok=False)
                self.assertIn("review", (blocked.stdout + blocked.stderr).lower())
                self.approve_fixture(ep)
                self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver")
                original_delivery = profile / "completed videos" / f"{spec['id']} - {spec['title']}"
                original_caption = (original_delivery / "caption.txt").read_bytes()
                # Reproduce the audit exactly: an approved episode's changed title must
                # not let caption,deliver reuse the old review, even though video is unchanged.
                spec["title"] = "Changed caption needs review"
                spec_file.write_text(json.dumps(spec), encoding="utf-8")
                self.run_command("pipeline/make_episode.py", ep, "--steps", "caption,deliver", ok=False)
                delivered = profile / "completed videos" / f"{spec['id']} - {spec['title']}"
                self.assertFalse(delivered.exists(), "changed captions were delivered using an old approval")
                self.assertEqual((original_delivery / "caption.txt").read_bytes(), original_caption)
                self.run_command("pipeline/make_episode.py", ep, "--steps", "qa")
                self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver", ok=False)
                self.approve_fixture(ep)
                # Re-encoding a cover after approval also requires a fresh review.
                cover = ep / "final" / "cover.jpg"
                with Image.open(cover) as im:
                    changed = im.convert("RGB")
                ImageDraw.Draw(changed).rectangle((0, 0, 150, 150), fill="magenta")
                changed.save(cover, quality=95)
                self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver", ok=False)
                self.run_command("pipeline/make_episode.py", ep, "--steps", "qa")
                self.run_command("pipeline/make_episode.py", ep, "--steps", "deliver", ok=False)
                self.approve_fixture(ep)
                shipped = self.run_command("pipeline/make_episode.py", ep, "--steps", "ship")
                self.assertIn("READY in ReelForge", shipped.stdout)
                self.assertEqual(hashlib.sha256(final.read_bytes()).digest(),
                                 hashlib.sha256((delivered / final.name).read_bytes()).digest())
                self.assertEqual((delivered / "cover.jpg").read_bytes(), cover.read_bytes())
                self.assertEqual((delivered / "caption.txt").read_bytes(), (ep / "final" / "caption.txt").read_bytes())
                (ep / "edit" / "index.html").write_text(html.replace("#14243d", "#223344"), encoding="utf-8")
                stale = self.run_command("pipeline/make_episode.py", ep, "--steps", "post", ok=False)
                self.assertIn("changed", stale.stdout + stale.stderr)
                evidence = {"native_os": platform.system(), "native_arch": platform.machine(), "node_arch": node_arch,
                            "duration": SECONDS, "frames": FPS * SECONDS,
                            "audio_transition_seconds": measured, "qa": "PASS", "manual_delivery": "PASS"}
                (self.artifacts / "acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence), flush=True)
            finally:
                # Retain only generated fixture evidence (never user data), on failure too.
                for relative in ("episode.json", "edit/index.html", "build/agentcut-render.json", "build/agentcut.mp4"):
                    source = ep / relative
                    if source.is_file():
                        shutil.copyfile(source, self.artifacts / source.name)
                for relative in ("build/qa", "final"):
                    source = ep / relative
                    if source.is_dir():
                        shutil.copytree(source, self.artifacts / source.name, dirs_exist_ok=True)
                if env_before is None:
                    os.environ.pop("STUDIO_BLENDER", None)
                else:
                    os.environ["STUDIO_BLENDER"] = env_before


if __name__ == "__main__":
    unittest.main()
