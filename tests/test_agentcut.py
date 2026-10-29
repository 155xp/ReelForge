"""Optional headless editing contracts, without installing Node, Chromium or Blender."""
import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from studio import agentcut, profiles, settings
from studio import paths as P
from studio.__main__ import new_episode

KIT = Path(__file__).resolve().parent.parent


def pipeline_module(name, config):
    """Load script modules without leaking their unqualified config import into other tests."""
    spec = importlib.util.spec_from_file_location("test_agentcut_" + name, KIT / "pipeline" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"config": config}), mock.patch.object(sys, "path", list(sys.path)):
        spec.loader.exec_module(module)
    return module


class Scratch(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ReelForge edit '")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for module, name, value in ((profiles, "ROOT", self.root), (profiles, "FOLDER", self.root / "profiles"),
                                    (P, "ROOT", self.root), (P, "TOOLS", self.root / "tools")):
            self.enterContext(mock.patch.object(module, name, value))
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop(profiles.ENV, None)

    def capture(self, args):
        with redirect_stdout(io.StringIO()) as output:
            status = agentcut.main(args)
        return status, json.loads(output.getvalue())

    def installed_script(self, version=agentcut.VERSION):
        package = agentcut.install_root() / "node_modules" / "hyperframes"
        (package / "bin").mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        script = package / "bin" / "hyperframes.mjs"
        script.write_text("// External engine fixture; never executed by these tests.\n", encoding="utf-8")
        return script


class HeadlessCommands(Scratch):
    def test_help_schema_and_status_work_without_optional_dependencies(self):
        with mock.patch.object(agentcut, "runtime", side_effect=AssertionError("must not start Node")), \
                mock.patch.object(agentcut, "install", side_effect=AssertionError("must not install")):
            status, guide = self.capture([])
            self.assertEqual(status, 0)
            self.assertTrue(guide["headless"])
            self.assertIn("open agentcut", guide["trigger"])
            status, schema = self.capture(["schema"])
            self.assertEqual(status, 0)
            self.assertEqual(schema["engine"], "HyperFrames")
            status, state = self.capture(["status"])
            self.assertEqual(status, 0)
            self.assertFalse(state["installed"])
        self.assertFalse(agentcut.install_root().exists())

    def test_doctor_uses_json_health_even_when_engine_exits_zero(self):
        for healthy in (False, True):
            checks = [{"name": name, "ok": healthy} for name in ("Node.js", "FFmpeg", "FFprobe", "Chrome")]
            checks += [{"name": "TTS (Kokoro)", "ok": False}]
            with self.subTest(healthy=healthy), mock.patch.object(agentcut, "invoke", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps({"ok": False, "checks": checks}), "")):
                status, result = self.capture(["doctor"])
                self.assertEqual(status, 0 if healthy else 1)
                self.assertEqual(result["ok"], healthy)
                self.assertFalse(result["engine_ok"])

    def test_invoke_uses_pinned_local_engine_and_preserves_spaced_paths(self):
        script = self.installed_script()
        edit = self.root / "episode with spaces" / "edit"
        with mock.patch.object(agentcut, "runtime", return_value="/node with spaces/node"), \
                mock.patch.object(agentcut.tools, "find_ffmpeg", return_value="/ffmpeg with spaces/ffmpeg"), \
                mock.patch.object(agentcut.subprocess, "run", return_value=
                                  subprocess.CompletedProcess([], 0, "{}", "")) as run:
            agentcut.invoke("info", edit, "--json")
        command = run.call_args.args[0]
        self.assertEqual(command, ["/node with spaces/node", str(script), "info", str(edit), "--json"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["HYPERFRAMES_NO_TELEMETRY"], "1")
        self.assertEqual(env["HYPERFRAMES_NO_UPDATE_CHECK"], "1")
        self.assertEqual(env["HYPERFRAMES_FFMPEG_PATH"], "/ffmpeg with spaces/ffmpeg")

    def test_a_different_installed_version_is_refused_without_updating(self):
        self.installed_script(version="0.0.0")
        with mock.patch.object(agentcut, "runtime", return_value="node"), \
                mock.patch.object(agentcut.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "version differs"):
                agentcut.invoke("info", self.root)
        run.assert_not_called()

    def test_tool_cannot_publish_or_start_cloud_work(self):
        for command in ("publish", "cloud", "lambda", "cloudrun", "upgrade", "install"):
            with self.subTest(command=command), mock.patch.object(agentcut, "invoke") as invoke:
                status, result = self.capture(["tool", command])
                self.assertEqual(status, 1)
                self.assertIn("Local editing tools", result["error"])
                invoke.assert_not_called()


class EpisodeSelection(Scratch):
    def setUp(self):
        super().setUp()
        self.s = copy.deepcopy(settings.DEFAULTS)
        self.s["video"]["backend"] = "agentcut"
        self.s["video"]["min_seconds"] = 30

    def save_settings(self):
        path = profiles.current().settings
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(settings.dump_toml(self.s), encoding="utf-8")

    def test_profile_backend_creates_local_draft_without_editor_installation(self):
        profile = profiles.create("Edited clips")
        profiles.use(profile)
        self.save_settings()
        with mock.patch.object(agentcut, "install", side_effect=AssertionError("drafts do not install")), \
                mock.patch.object(agentcut, "invoke", side_effect=AssertionError("drafts do not render")), \
                mock.patch.object(agentcut.tools, "find_blender", side_effect=AssertionError("no Blender needed")), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(new_episode(["ocean", "--topic", "Why the ocean looks blue"]), 0)
        ep = profile.episodes / "ep01_ocean"
        spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["backend"], "agentcut")
        self.assertEqual(spec["audio"]["mixer"], "agentcut")
        self.assertEqual(spec["duration"], 30)
        self.assertTrue((ep / "edit" / "index.html").is_file())
        self.assertTrue((ep / "edit" / "media").is_dir())
        self.assertIn("Why the ocean looks blue", (ep / "agentcut-task.md").read_text(encoding="utf-8"))
        self.assertTrue((ep / "facts.md").is_file())
        self.assertFalse((self.root / "episodes").exists())
        self.assertFalse(agentcut.install_root().exists())

    def test_per_video_override_does_not_change_channel_default(self):
        self.save_settings()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(new_episode(["simulation", "--backend", "blender"]), 0)
        spec = json.loads((profiles.current().episodes / "ep01_simulation" / "episode.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["backend"], "blender")
        self.assertIn("world", spec)
        self.assertFalse(spec.get("demo", False))
        self.assertEqual(settings.load()["video"]["backend"], "agentcut")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(agentcut.main(["new", "cut", "--topic", "A real edit"]), 0)
        second = profiles.current().episodes / "ep02_cut"
        self.assertEqual(json.loads((second / "episode.json").read_text())["backend"], "agentcut")


class EpisodeValidation(Scratch):
    def setUp(self):
        super().setUp()
        self.ep = self.root / "episode"
        self.ep.mkdir()
        self.spec = {"backend": "agentcut", "fps": 30, "duration": 3, "render_until": 3}

    def validate(self, metadata=None):
        (self.ep / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        metadata = metadata or {"width": 1080, "height": 1920, "duration": 3}
        with mock.patch.object(agentcut, "prepare", return_value=self.ep / "edit"), \
                mock.patch.object(agentcut, "call", side_effect=[{}, metadata]):
            return agentcut.validate_episode(self.ep)

    def test_valid_metadata_returns_exact_frame_count(self):
        self.assertEqual(self.validate()["frames"], 90)

    def test_episode_timing_cannot_drift_or_exceed_final_duration(self):
        for changes in ({"fps": 24}, {"duration": float("nan")}, {"render_until": True},
                        {"render_until": 4}, {"duration": 3.01}, {"render_until": 2.01}):
            with self.subTest(changes=changes):
                original = self.spec.copy()
                self.spec.update(changes)
                with self.assertRaises(ValueError):
                    self.validate()
                self.spec = original

    def test_engine_composition_must_match_delivery_dimensions_and_duration(self):
        for metadata in ({"width": 1920, "height": 1080, "duration": 3},
                         {"width": 1080, "height": 1920, "duration": float("nan")},
                         {"width": 1080, "height": 1920, "duration": 2.5}):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                self.validate(metadata)


class RenderFreshness(Scratch):
    def setUp(self):
        super().setUp()
        self.ep = self.root / "episode"
        (self.ep / "edit" / "media").mkdir(parents=True)
        self.source = self.ep / "edit" / "media" / "source.mp4"
        self.source.write_bytes(b"original")
        (self.ep / "edit" / "index.html").write_text("<html>composition</html>", encoding="utf-8")
        self.spec = {"id": "ep01_edit", "backend": "agentcut", "fps": 30,
                     "duration": 0.1, "render_until": 0.1}
        (self.ep / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        self.config = SimpleNamespace(PIPELINE=KIT / "pipeline", require_ffmpeg=mock.Mock(return_value="ffmpeg"),
                                     require_blender=mock.Mock(side_effect=AssertionError("no Blender")))
        self.bridge = pipeline_module("agentcut", self.config)
        self.edit = self.bridge.Edit(self.ep, self.spec)
        (self.ep / "build").mkdir()

    def commit_render(self):
        self.edit.video.write_bytes(b"render fixture")
        self.edit.manifest.write_text(json.dumps({"source": self.bridge.fingerprint(self.ep, self.spec)}))
        frames = self.ep / "build" / "frames"
        frames.mkdir(exist_ok=True)
        for index in range(1, 4):
            (frames / f"f_{index:04d}.jpg").write_bytes(b"frame fixture")

    def test_same_size_asset_change_invalidates_render_even_with_same_mtime(self):
        self.commit_render()
        self.edit.require_render()
        stamp = self.source.stat().st_mtime_ns
        self.source.write_bytes(b"modified")
        os.utime(self.source, ns=(stamp, stamp))
        with self.assertRaisesRegex(ValueError, "media changed"):
            self.edit.require_render()

    def test_post_stops_before_mixing_for_missing_or_stale_render(self):
        pipeline = pipeline_module("make_episode", self.config)
        for state in ("missing", "stale"):
            if state == "stale":
                self.commit_render()
                self.source.write_bytes(b"revised source")
            with self.subTest(state=state), mock.patch.dict(sys.modules, {"agentcut": self.bridge}), \
                    mock.patch.object(sys, "argv", ["make_episode", str(self.ep), "--steps", "post"]), \
                    mock.patch.object(pipeline, "run") as run:
                with self.assertRaisesRegex(ValueError, "render step"):
                    pipeline.main()
                run.assert_not_called()
        self.config.require_blender.assert_not_called()

    def test_missing_frames_require_rerender(self):
        self.commit_render()
        (self.ep / "build" / "frames" / "f_0002.jpg").unlink()
        with self.assertRaisesRegex(ValueError, "frames are missing"):
            self.edit.require_render()

    def test_video_requires_mastered_audio_after_render(self):
        self.commit_render()
        pipeline = pipeline_module("make_episode", self.config)
        with mock.patch.dict(sys.modules, {"agentcut": self.bridge}), \
                mock.patch.object(sys, "argv", ["make_episode", str(self.ep), "--steps", "video"]), \
                mock.patch.object(pipeline, "run") as run:
            with self.assertRaisesRegex(ValueError, "audio is missing"):
                pipeline.main()
            run.assert_not_called()

    def test_hidden_assets_and_nested_renders_folders_invalidate_render(self):
        for relative in ("media/.clip.mp4", "media/renders/clip.mp4"):
            asset = self.ep / "edit" / relative
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(b"first")
            self.commit_render()
            asset.write_bytes(b"other")
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "media changed"):
                self.edit.require_render()


if __name__ == "__main__":
    unittest.main()
