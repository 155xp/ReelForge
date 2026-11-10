"""Bridge HyperFrames edits into ReelForge's existing post-production and QA."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from fractions import Fraction

import config
from studio import agentcut, tools
from studio.agentcut_sources import file_hash, fingerprint, snapshot


class Edit:
    def __init__(self, ep, spec):
        self.ep, self.spec = ep, spec
        self.build = ep / "build"
        self.video = self.build / "agentcut.mp4"
        self.manifest = self.build / "agentcut-render.json"
        self.rendered = False

    def validate(self):
        result = agentcut.validate_episode(self.ep)
        series = {"fps": self.spec["fps"], "frames": result["frames"]}
        (self.build / "series.json").write_text(json.dumps(series) + "\n", encoding="utf-8")

    def frame_hashes(self, folder=None):
        folder = folder or self.build / "frames"
        count = round(self.spec["render_until"] * self.spec["fps"])
        names = [f"f_{index:04d}.jpg" for index in range(1, count + 1)]
        actual = sorted(path.name for path in folder.glob("f_*.jpg"))
        if actual != sorted(names) or any(not (folder / name).is_file() for name in names):
            raise ValueError("AgentCut frames are missing or renamed; rerun the render step")
        return {name: file_hash(folder / name) for name in names}

    def write_manifest(self, source):
        self.manifest.write_text(json.dumps({"schema": 2, "source": source, "engine": "HyperFrames",
                                             "version": agentcut.VERSION, "video": file_hash(self.video),
                                             "frames": self.frame_hashes()}, sort_keys=True) + "\n", encoding="utf-8")

    def require_source(self):
        if not self.video.is_file() or not self.manifest.is_file():
            raise ValueError("Run the AgentCut render step before post-production")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        if manifest.get("source") != fingerprint(self.ep, self.spec):
            raise ValueError("The edit or its media changed; rerun the AgentCut render step before post-production")
        if manifest.get("schema") != 2 or manifest.get("video") != file_hash(self.video):
            raise ValueError("AgentCut rendered video changed or has no content manifest; rerun the render step")
        return manifest

    def require_render(self):
        manifest = self.require_source()
        if manifest.get("frames") != self.frame_hashes():
            raise ValueError("AgentCut rendered frames changed; rerun the render step")

    def frames(self):
        if self.rendered:
            return
        self.validate()
        before = fingerprint(self.ep, self.spec)
        # Invalidate approval before changing any render artifacts.
        self.manifest.unlink(missing_ok=True)
        (self.build / "audio.wav").unlink(missing_ok=True)
        for name in ("qa.json", "review.md"):
            (self.build / "qa" / name).unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix=".agentcut-render-", dir=self.build) as tmp:
            temporary = Path(tmp)
            video = temporary / "edit.mp4"
            source = temporary / "source"
            snapshot(self.ep / "edit", source)
            agentcut.invoke("render", source, "--output", video, "--fps", str(self.spec["fps"]),
                            "--workers", "1", "--strict", "--no-best-effort", "--json")
            probe = subprocess.run([tools.ffprobe_for(config.require_ffmpeg()), "-v", "error",
                                    "-count_frames", "-show_streams", "-show_format", "-of", "json", str(video)],
                                   check=True, capture_output=True, text=True)
            info = json.loads(probe.stdout)
            stream = next(s for s in info["streams"] if s["codec_type"] == "video")
            if (stream["width"], stream["height"]) != (1080, 1920) or abs(
                    float(info["format"]["duration"]) - self.spec["render_until"]) > 0.1:
                raise ValueError("HyperFrames rendered dimensions or duration do not match the episode")
            count = round(self.spec["render_until"] * self.spec["fps"])
            if int(stream.get("nb_read_frames", 0)) != count or Fraction(stream["avg_frame_rate"]) != self.spec["fps"]:
                raise ValueError("HyperFrames rendered frame count or frame rate does not match the episode")
            frames = temporary / "frames"
            frames.mkdir()
            subprocess.run([config.require_ffmpeg(), "-v", "error", "-y", "-i", str(video),
                            "-an", "-frames:v", str(count), "-q:v", "2", str(frames / "f_%04d.jpg")], check=True)
            self.frame_hashes(frames)
            if fingerprint(self.ep, self.spec) != before:
                raise ValueError("Source media changed during rendering; rerun the render step")
            old = self.build / "frames"
            if old.exists():
                shutil.rmtree(old)
            frames.rename(old)
            video.replace(self.video)
            self.write_manifest(before)
        self.rendered = True

    def stills(self, seconds):
        # Preview and full render share one committed picture/audio pair, including across separate commands.
        self.frames()
        dest = self.build / "stills"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir()
        for second in seconds:
            if not 0 <= second < self.spec["render_until"]:
                raise ValueError(f"still time {second} is outside the edited timeline")
            frame = min(round(second * self.spec["fps"]), round(self.spec["render_until"] * self.spec["fps"]) - 1) + 1
            shutil.copyfile(self.build / "frames" / f"f_{frame:04d}.jpg", dest / f"s_{frame:04d}.jpg")
