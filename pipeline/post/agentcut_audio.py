"""Extract the edit's explicit audio tracks and master them to this channel's target."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from studio import tools
sys.path.insert(0, str(Path(__file__).resolve().parent))
from loudness import master


def make(ep):
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    source = ep / "build" / "agentcut.mp4"
    if not source.is_file():
        raise ValueError("Render the AgentCut timeline before its audio")
    audio = np.zeros((round(spec["duration"] * config.SAMPLE_RATE), 2), dtype=np.float32)
    probe = subprocess.run([tools.ffprobe_for(config.require_ffmpeg()), "-v", "error", "-show_streams",
                            "-of", "json", str(source)], check=True, capture_output=True, text=True)
    if any(s["codec_type"] == "audio" for s in json.loads(probe.stdout)["streams"]):
        raw = subprocess.run([config.require_ffmpeg(), "-v", "error", "-i", str(source), "-vn", "-ar", "48000",
                              "-ac", "2", "-f", "f32le", "-"], check=True, capture_output=True).stdout
        source_audio = np.frombuffer(raw, dtype="<f4").reshape(-1, 2)
        n = min(len(source_audio), len(audio))
        audio[:n] = source_audio[:n]
    if np.any(audio):
        audio, _, _ = master(audio)
    with wave.open(str(ep / "build" / "audio.wav"), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(config.SAMPLE_RATE)
        out.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    make(Path(sys.argv[1]).resolve())
