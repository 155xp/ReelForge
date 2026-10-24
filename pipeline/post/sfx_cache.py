"""Convert every sound in assets/sfx/manifest.json to 48 kHz stereo 16-bit WAV in assets/sfx/_cache/<name>.wav.

  python pipeline/post/sfx_cache.py          # converts anything missing
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

SFX = config.ROOT / "assets" / "sfx"


def cached(name):
    return SFX / "_cache" / f"{name}.wav"


def build_cache(force=False):
    manifest = json.loads((SFX / "manifest.json").read_text(encoding="utf-8"))
    (SFX / "_cache").mkdir(exist_ok=True)
    missing = [n for n, m in manifest["sounds"].items() if not (SFX / m["file"]).exists() and not cached(n).exists()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} sounds aren't downloaded yet ({', '.join(missing[:4])}"
                                f"{', ...' if len(missing) > 4 else ''}). Run setup again, or: python -m studio sounds")
    for name, meta in manifest["sounds"].items():
        src = SFX / meta["file"]
        out = cached(name)
        if out.exists() and not force:
            continue
        if not src.exists():
            continue
        subprocess.run([config.require_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-ac", "2", "-ar", str(config.SAMPLE_RATE),
                        "-c:a", "pcm_s16le", str(out)], check=True)
        print(f"  cached {name}")
    return manifest


if __name__ == "__main__":
    build_cache(force="--force" in sys.argv)
