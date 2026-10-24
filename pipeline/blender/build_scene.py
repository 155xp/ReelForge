"""Blender entry point: build an episode's scene from its spec and save build/scene.blend + build/series.json.

Usage (normally via make_episode.py):
  blender -b --factory-startup -P pipeline/blender/build_scene.py -- <episode_dir>
"""
import importlib
import json
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rf_common as rf  # noqa: E402

ep_dir = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
spec = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
build = ep_dir / "build"
(build / "frames").mkdir(parents=True, exist_ok=True)

rf.clear_scene()
scene = bpy.context.scene
rf.setup_render(scene, spec, build)

world = importlib.import_module("worlds." + spec["world"]["type"])
info = world.build(spec)
effect = importlib.import_module("effects." + spec["effect"]["type"])
series = effect.apply(spec, info)

(build / "series.json").write_text(json.dumps(series), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(build / "scene.blend"))
print(f"[build_scene] saved {build / 'scene.blend'}")
