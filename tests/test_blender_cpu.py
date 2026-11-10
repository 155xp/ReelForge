"""The opt-in CPU renderer must retain full resolution without changing default Blender workflows."""

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


class BlenderCpuFallback(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "pipeline/blender/rf_common.py"
        spec = importlib.util.spec_from_file_location("rf_common_cpu_test", source)
        self.helpers = importlib.util.module_from_spec(spec)
        with mock.patch.dict("sys.modules", {"bpy": SimpleNamespace(), "bmesh": SimpleNamespace()}):
            spec.loader.exec_module(self.helpers)
        self.scene = SimpleNamespace(render=SimpleNamespace(image_settings=SimpleNamespace()),
                                     cycles=SimpleNamespace(device="GPU", samples=128),
                                     eevee=SimpleNamespace(), view_settings=SimpleNamespace())
        self.spec = {"fps": 30, "render_until": 67, "render": {"samples": 16}}

    def test_default_and_unselected_override_keep_eevee(self):
        for value in ("", "0", "false"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"STUDIO_BLENDER_CPU": value}):
                self.helpers.setup_render(self.scene, self.spec, Path("build"))
                self.assertEqual(self.scene.render.engine, "BLENDER_EEVEE_NEXT")
                self.assertEqual(self.scene.cycles.device, "GPU")
                self.assertEqual(self.scene.cycles.samples, 128)

    def test_explicit_cpu_mode_preserves_dimensions_timing_and_samples(self):
        with mock.patch.dict(os.environ, {"STUDIO_BLENDER_CPU": "1"}):
            self.helpers.setup_render(self.scene, self.spec, Path("build"))
        self.assertEqual(self.scene.render.engine, "CYCLES")
        self.assertEqual(self.scene.cycles.device, "CPU")
        self.assertEqual(self.scene.cycles.samples, 16)
        self.assertEqual((self.scene.render.resolution_x, self.scene.render.resolution_y,
                          self.scene.render.resolution_percentage), (1080, 1920, 100))
        self.assertEqual((self.scene.render.fps, self.scene.frame_start, self.scene.frame_end), (30, 1, 2010))
        self.assertEqual(self.scene.render.image_settings.file_format, "JPEG")
        self.assertFalse(self.scene.render.use_overwrite)


if __name__ == "__main__":
    unittest.main()
