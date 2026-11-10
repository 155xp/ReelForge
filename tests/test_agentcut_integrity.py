"""Regressions for tracked local dependencies and the rendered picture/audio pair."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from studio import agentcut_sources as sources
from tests.test_agentcut import pipeline_module


class SourceAndRenderIntegrity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="AgentCut local files ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ep = self.root / "episode"
        self.edit = self.ep / "edit"
        (self.edit / "media").mkdir(parents=True)
        self.html = self.edit / "index.html"
        self.html.write_text('<html><head></head><body><img src="media/source.png"></body></html>')
        (self.edit / "media" / "source.png").write_bytes(b"image fixture")
        self.spec = {"fps": 30, "render_until": 0.1}
        self.bridge = pipeline_module("agentcut", SimpleNamespace())
        self.render = self.bridge.Edit(self.ep, self.spec)
        self.render.build.mkdir()
        self.render.video.write_bytes(b"original video and audio")
        frames = self.render.build / "frames"
        frames.mkdir()
        for index in range(1, 4):
            (frames / f"f_{index:04d}.jpg").write_bytes(f"picture {index}".encode())

    def commit(self):
        self.render.write_manifest(sources.fingerprint(self.ep, self.spec))
        self.render.require_render()

    def test_symlinked_directory_asset_change_invalidates_same_size_same_mtime(self):
        outside = self.root / "source footage"
        outside.mkdir()
        clip = outside / "clip.mp4"
        clip.write_bytes(b"original")
        (self.edit / "media" / "linked clips").symlink_to(outside, target_is_directory=True)
        self.commit()
        stamp = clip.stat().st_mtime_ns
        clip.write_bytes(b"modified")
        os.utime(clip, ns=(stamp, stamp))
        with self.assertRaisesRegex(ValueError, "media changed"):
            self.render.require_render()

    def test_symlinked_file_change_and_retarget_are_tracked(self):
        first = self.root / "one.png"
        second = self.root / "two.png"
        first.write_bytes(b"first")
        second.write_bytes(b"other")
        link = self.edit / "media" / "linked.png"
        link.symlink_to(first)
        self.commit()
        link.unlink()
        link.symlink_to(second)
        with self.assertRaisesRegex(ValueError, "media changed"):
            self.render.require_render()

    def test_broken_and_cyclic_symlinks_fail_clearly(self):
        link = self.edit / "media" / "link"
        link.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "broken AgentCut source"):
            sources.fingerprint(self.ep, self.spec)
        link.unlink()
        link.symlink_to(self.edit, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Cyclic AgentCut"):
            sources.fingerprint(self.ep, self.spec)

    def test_replacing_render_video_cannot_mix_new_audio_with_retained_frames(self):
        self.commit()
        self.render.video.write_bytes(b"different video and tone")
        with self.assertRaisesRegex(ValueError, "rendered video changed"):
            self.render.require_render()

    def test_renaming_frame_with_same_count_is_rejected(self):
        self.commit()
        frames = self.render.build / "frames"
        (frames / "f_0002.jpg").rename(frames / "f_9999.jpg")
        with self.assertRaisesRegex(ValueError, "missing or renamed"):
            self.render.require_render()

    def test_changing_frame_bytes_with_same_name_and_count_is_rejected(self):
        self.commit()
        (self.render.build / "frames" / "f_0002.jpg").write_bytes(b"picture 9")
        with self.assertRaisesRegex(ValueError, "frames changed"):
            self.render.require_render()

    def test_legacy_manifest_cannot_be_treated_as_verified_render(self):
        self.render.manifest.write_text(json.dumps({"source": sources.fingerprint(self.ep, self.spec)}))
        with self.assertRaisesRegex(ValueError, "content manifest"):
            self.render.require_render()

    def test_delivery_source_check_survives_intentional_frame_cleanup(self):
        self.commit()
        for frame in (self.render.build / "frames").iterdir():
            frame.unlink()
        self.render.require_source()

    def test_remote_or_untracked_dependencies_are_rejected(self):
        for content in (
            '<video src="https://example.invalid/movie.mp4"></video>',
            '<audio src="//example.invalid/audio.wav"></audio>',
            '<video src="data:application/vnd.apple.mpegurl,%23EXTM3U%0A/tmp/untracked.ts"></video>',
            '<video src="data:application/octet-stream;base64,I0VYVE0zVQo="></video>',
            '<img src="data:image/svg+xml,%3Csvg%3E%3C/svg%3E">',
            '<img src="file:///tmp/outside.png">',
            '<style>@font-face{src:url(https://example.invalid/font.woff)}</style>',
            '<link rel="stylesheet" href="https://example.invalid/style.css">',
            '<style>@import "https://example.invalid/style.css";</style>',
            '<img src="../outside.png">',
            '<img src="%2e%2e/outside.png">',
            '<video src="renders/previous.mp4"></video>',
            '<script>fetch("media/source.png")</script>',
            '<script type="module">import value from "../untracked.js";</script>',
            '<script>const url = "https://example.invalid/movie.mp4";</script>',
            '<base href="media/"><img src="source.png">',
            '<div data-composition-src="../outside.html"></div>',
            '<div data-composition-file="https&#58;//example.invalid/scene.html"></div>',
            '<div data-lottie-src="https&#58;//example.invalid/animation.json"></div>',
        ):
            with self.subTest(content=content):
                self.html.write_text(content)
                with self.assertRaises(ValueError):
                    sources.validate_local_sources(self.edit)

    def test_playlists_are_rejected_even_with_misleading_media_extension(self):
        for name, content in (
            ("playlist.m3u8", b"#EXTM3U\nhttps://example.invalid/media.ts"),
            ("pretend.mp4", b"#EXTM3U\nhttps://example.invalid/media.ts"),
            ("pretend.mp4", b"ffconcat version 1.0\nfile 'https://example.invalid/media.mp4'"),
            ("pretend.mp4", b'<?xml version="1.0"?><MPD><BaseURL>https://example.invalid/</BaseURL></MPD>'),
            ("pretend.mp4", b"v=0\no=- 0 0 IN IP4 127.0.0.1\n"),
            ("playlist.mpd", b"manifest fixture"),
        ):
            with self.subTest(name=name, content=content):
                asset = self.edit / "media" / name
                asset.write_bytes(content)
                try:
                    with self.assertRaisesRegex(ValueError, "media playlist"):
                        sources.validate_local_sources(self.edit)
                finally:
                    asset.unlink()

    def test_local_spaced_paths_fonts_and_nested_css_are_supported_and_hashed(self):
        font = self.edit / "media" / "font with spaces.woff"
        font.write_bytes(b"font fixture")
        styles = self.edit / "styles"
        styles.mkdir()
        (styles / "main.css").write_text('@font-face{src:url("../media/font%20with%20spaces.woff")}')
        self.html.write_text('<html><head><link rel="stylesheet" href="styles/main.css"></head></html>')
        sources.validate_local_sources(self.edit)
        before = sources.fingerprint(self.ep, self.spec)
        font.write_bytes(b"changed font")
        self.assertNotEqual(before, sources.fingerprint(self.ep, self.spec))

    def test_snapshot_policy_precedes_authored_resources_and_fake_head_tags(self):
        for original in (
            '<!-- <head> --> <html><head><script>window.example = true;</script></head></html>',
            '<script>const text = "<head>";</script><html><head></head></html>',
            '<!doctype html><img src="media/source.png"><html><head></head></html>',
        ):
            with self.subTest(original=original):
                self.html.write_text(original)
                destination = self.root / "policy snapshot"
                sources.snapshot(self.edit, destination)
                staged = (destination / "index.html").read_text()
                self.assertTrue(staged.startswith('<!doctype html>\n<meta http-equiv="Content-Security-Policy"'))
                self.assertLess(staged.index("Content-Security-Policy"), staged.index("<head>"))

    def test_render_snapshot_resolves_links_and_enforces_local_resource_policy(self):
        outside = self.root / "linked image.png"
        outside.write_bytes(b"linked pixels")
        (self.edit / "media" / "linked.png").symlink_to(outside)
        destination = self.root / "render snapshot"
        sources.snapshot(self.edit, destination)
        copied = destination / "media" / "linked.png"
        self.assertFalse(copied.is_symlink())
        self.assertEqual(copied.read_bytes(), b"linked pixels")
        self.assertIn(sources.CSP, (destination / "index.html").read_text())
        self.assertNotIn("Content-Security-Policy", self.html.read_text())


if __name__ == "__main__":
    unittest.main()
