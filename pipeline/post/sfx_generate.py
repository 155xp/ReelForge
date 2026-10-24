"""Synthesize a few short, tonal sound effects into assets/sfx/generated/*.wav and register them in the manifest
(they are then cached like any other sound).

Only short tonal accents belong here. Never synthesize ambience or long effects out of noise (surf, crowds, rain,
wind, engines): surf and crowd beds made this way were heard as "super loud static". Beds come from real
recordings in assets/sfx; qa.py fails a video that has stretches of static.

  python pipeline/post/sfx_generate.py          # writes any that are missing
  python pipeline/post/sfx_generate.py --force

Sounds:
  coins         2 s: a spray of coins clinking
  kaching       1.2 s: cash register (drawer clunk + bell)
  shimmer       1.6 s: a bright rising magic shimmer
  shutter       0.2 s: a camera shutter click
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

SR = config.SAMPLE_RATE
SFX = config.ROOT / "assets" / "sfx"
OUT = SFX / "generated"


def _lp(x, cutoff):
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (f / max(cutoff, 1.0)) ** 4), n=len(x))


def _bp(x, lo, hi):
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    X = np.fft.rfft(x)
    g = 1.0 / np.sqrt(1 + (f / max(hi, 1.0)) ** 4) * (1.0 - 1.0 / np.sqrt(1 + (f / max(lo, 1.0)) ** 4))
    return np.fft.irfft(X * g, n=len(x))



def _norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def _st(m, width=0.0, rng=None):
    if width and rng is not None:
        d = int(0.012 * SR)
        r = np.roll(m, d)
        return np.stack([m * (1 - width) + r * width, m], 1)
    return np.stack([m, m], 1)


def ping(f, dur, rng, decay=9.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 2.76 * t + 1.0) * np.exp(-t * 4)
         + 0.35 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 7))
    return s * np.minimum(1.0, t / 0.0015) * np.exp(-t * decay)


def coins(rng, dur=2.0):
    n = int(dur * SR)
    m = np.zeros(n)
    for _ in range(60):
        t0 = rng.uniform(0.0, 1.3) ** 1.6
        f = rng.uniform(2600, 6200)
        p = ping(f, 0.5, rng, rng.uniform(10, 22)) * rng.uniform(0.2, 1.0)
        i = int(t0 * SR)
        m[i:i + len(p)] += p[: n - i]
    return _st(_norm(m, 0.85), 0.4, rng)


def kaching(rng, dur=1.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    clunk = _lp(rng.standard_normal(n), 1800.0) * np.exp(-t * 60.0) * 1.2
    clunk += np.sin(2 * np.pi * 120 * t) * np.exp(-t * 30.0) * 0.6
    bell = np.zeros(n)
    t1 = 0.06
    for f, a, d in ((2100.0, 1.0, 3.2), (3420.0, 0.6, 4.0), (5230.0, 0.35, 6.0), (1040.0, 0.25, 2.5)):
        bell += a * np.sin(2 * np.pi * f * np.clip(t - t1, 0, None)) * np.exp(-np.clip(t - t1, 0, None) * d) * (t > t1)
    return _st(_norm(clunk + bell * 0.8, 0.9))


def shimmer(rng, dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    m = np.zeros(n)
    for _ in range(40):
        f = rng.uniform(1800, 7000) * (1 + 0.5 * u)
        ph = np.cumsum(2 * np.pi * f / SR)
        trem = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(8, 25) * t + rng.uniform(0, 6))
        m += np.sin(ph) * trem * rng.uniform(0.2, 1.0)
    env = np.sin(np.pi * u) ** 1.5 * (0.4 + 0.6 * u)
    return _st(_norm(m * env, 0.7), 0.5, rng)


def shutter(rng, dur=0.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    m = np.zeros(n)
    for t0, a in ((0.0, 1.0), (0.055, 0.7)):
        i = int(t0 * SR)
        k = n - i
        tt = np.arange(k) / SR
        click = _bp(rng.standard_normal(k), 1500.0, 9000.0) * np.exp(-tt * 140.0) * a
        click += np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 90.0) * 0.4 * a
        m[i:] += click
    return _st(_norm(m, 0.9))


SOUNDS = {"coins": coins, "kaching": kaching, "shimmer": shimmer, "shutter": shutter}


def write(name, x):
    OUT.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main(force=False):
    mpath = SFX / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    changed = False
    for k, (name, fn) in enumerate(SOUNDS.items()):
        f = OUT / f"{name}.wav"
        if force or not f.exists():
            write(name, fn(np.random.default_rng(100 + k)))
            print(f"  generated {name}")
        if name not in manifest["sounds"]:
            manifest["sounds"][name] = {"file": f"generated/{name}.wav", "license": "generated (pipeline/post/sfx_generate.py)"}
            changed = True
    if changed:
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("  manifest updated")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
