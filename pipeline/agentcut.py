"""Bridge HyperFrames edits into ReelForge's existing post-production and QA."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import config
from studio import agentcut, tools


def fingerprint(ep, spec):
    digest = hashlib.sha256(json.dumps({k: spec[k] for k in ("fps", "render_until")}, sort_keys=True).encode())
    edit = ep / "edit"
    for source in sorted(edit.rglob("*")):
        relative = source.relative_to(edit)
        if not source.is_file() or relative.parts[0] in (".hyperframes", "node_modules", "renders"):
            continue
        digest.update(relative.as_posix().encode())
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


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

    def require_source(self):
        if not self.video.is_file() or not self.manifest.is_file():
            raise ValueError("Run the AgentCut render step before post-production")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        if manifest.get("source") != fingerprint(self.ep, self.spec):
            raise ValueError("The edit or its media changed; rerun the AgentCut render step before post-production")

    def require_render(self):
        self.require_source()
        count = round(self.spec["render_until"] * self.spec["fps"])
        if len(list((self.build / "frames").glob("f_*.jpg"))) != count:
            raise ValueError("AgentCut frames are missing; rerun the render step")

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
            agentcut.invoke("render", self.ep / "edit", "--output", video, "--fps", str(self.spec["fps"]),
                            "--workers", "1", "--strict", "--no-best-effort", "--json")
            probe = subprocess.run([tools.ffprobe_for(config.require_ffmpeg()), "-v", "error",
                                    "-show_streams", "-show_format", "-of", "json", str(video)],
                                   check=True, capture_output=True, text=True)
            info = json.loads(probe.stdout)
            stream = next(s for s in info["streams"] if s["codec_type"] == "video")
            if (stream["width"], stream["height"]) != (1080, 1920) or abs(
                    float(info["format"]["duration"]) - self.spec["render_until"]) > 0.1:
                raise ValueError("HyperFrames rendered dimensions or duration do not match the episode")
            frames = temporary / "frames"
            frames.mkdir()
            count = round(self.spec["render_until"] * self.spec["fps"])
            subprocess.run([config.require_ffmpeg(), "-v", "error", "-y", "-i", str(video),
                            "-an", "-frames:v", str(count), "-q:v", "2", str(frames / "f_%04d.jpg")], check=True)
            if len(list(frames.glob("f_*.jpg"))) != count:
                raise ValueError("HyperFrames did not render the expected number of frames")
            if fingerprint(self.ep, self.spec) != before:
                raise ValueError("Source media changed during rendering; rerun the render step")
            old = self.build / "frames"
            if old.exists():
                shutil.rmtree(old)
            frames.rename(old)
            video.replace(self.video)
            self.manifest.write_text(json.dumps({"source": before, "engine": "HyperFrames",
                                                 "version": agentcut.VERSION}) + "\n", encoding="utf-8")
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
