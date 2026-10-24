"""Sample-based sound design driven by a cue sheet in episode.json ("audio": {"mixer": "samples", ...}).

Sounds come from assets/sfx/manifest.json (cached as 48 kHz WAV by sfx_cache.py). Cue types:
  beds     looped sound over [from, to) with gain/rate curves [[t, v], ...] (rate "gears" = engine pitch per doubling)
  hits     one-shot at "at"; "align": "start" | "peak" (loudest moment lands on "at") | "end"
  scatter  one random sound from "pool" per cluster of series events (e.g. every window burst)
  ticks    synthesized blip at every time in a series event list (e.g. each doubling)
  rewind   the finished mix of [source] played backwards into [from, to) (accelerating, like the picture)
  cut_at   everything except hits/rewind stops dead here
Writes build/audio.wav.
"""
import json
import math
import random
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from post.loudness import master  # noqa: E402
from post.sfx_cache import build_cache, cached  # noqa: E402

SR = config.SAMPLE_RATE
_cache = {}


def load(name):
    if name not in _cache:
        with wave.open(str(cached(name))) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, w.getnchannels()).astype(np.float32)
        _cache[name] = x / 32768.0
    return _cache[name]


def curve(points, t):
    if isinstance(points, (int, float)):
        return np.full_like(t, float(points))
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


def gear_rate(t, doubling_start=2.0, period=2.0):
    """Engine pitch: idle, then revs up through a 'gear' every doubling and drops back a little."""
    k = np.clip((t - doubling_start) / period, 0, None)
    within = k - np.floor(k)
    rate = 0.62 + 0.5 * within ** 0.8 + 0.06 * np.minimum(np.floor(k), 9)
    return np.where(t < doubling_start, 0.55, rate)


def loopable(x, xf=int(0.3 * SR)):
    if len(x) < 3 * xf:
        return x
    ramp = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
    y = x[:-xf].copy()
    y[:xf] = x[:xf] * ramp + x[-xf:] * (1 - ramp)
    return y


def play(x, n, rate, offset=0.0, loop=True):
    """Resample x to n output samples at a (possibly per-sample) playback rate."""
    rate = np.broadcast_to(np.asarray(rate, dtype=np.float64), (n,))
    phase = offset * SR + np.concatenate([[0.0], np.cumsum(rate[:-1])])
    if loop:
        phase = np.mod(phase, len(x) - 1)
    else:
        phase = np.clip(phase, 0, len(x) - 1.001)
    i0 = np.floor(phase).astype(np.int64)
    f = (phase - i0)[:, None].astype(np.float32)
    out = x[i0] * (1 - f) + x[np.minimum(i0 + 1, len(x) - 1)] * f
    if not loop:
        out[phase >= len(x) - 1.001] = 0
    return out


def add(buf, sig, t0, pan=0.0):
    i0 = int(round(t0 * SR))
    if i0 >= len(buf):
        return
    if i0 < 0:
        sig, i0 = sig[-i0:], 0
    sig = sig[:len(buf) - i0]
    if pan:
        sig = sig * np.array([min(1.0, 1 - pan), min(1.0, 1 + pan)], dtype=np.float32)
    buf[i0:i0 + len(sig)] += sig


def peak_time(x):
    env = np.convolve(np.abs(x).mean(1), np.ones(int(0.02 * SR)) / (0.02 * SR), mode="same")
    return float(np.argmax(env)) / SR


# ---------------------------------------------------------------- synthesized sounds (cue key "synth")

def _lp(x, cutoff):
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (f / max(cutoff, 1.0)) ** 4), n=len(x))


def _stereo(m, pan=0.0):
    return np.stack([m * min(1.0, 1 - pan), m * min(1.0, 1 + pan)], 1).astype(np.float32)


def synth(name, p, rng):
    """Short synthesized effects. Returns a stereo float32 buffer.
      ding    elevator chime (freq), bell partials with a soft attack
      notify  a phone notification: two quick bright tones a fourth apart (freq = the first)
      jet     airliner fly-by: rushing noise with a falling whine, swept left to right
      pop     balloon pop: a hard crack, a burst of noise and a low thump
      squeak  rubber stretching: a wobbling upward sweep
      whoosh  band-swept noise burst (dur)
      coin    one bright coin 'ping' (freq), for per-doubling ticks
      shutter a camera shutter click
    jet and whoosh are made of filtered white noise and read as static in a mix (a jet fly-by fails qa.py's hiss check):
    don't use them in new episodes; use recordings (rocket_turbine, meteor_whoosh, speed_swoosh) instead."""
    if name == "ding":
        f = p.get("freq", 740.0)
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        env = np.minimum(1.0, t / 0.004) * np.exp(-t * 2.6)
        sig = (np.sin(2 * np.pi * f * t) + 0.32 * np.sin(2 * np.pi * 2.0 * f * t) * np.exp(-t * 3.5)
               + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 6.0)
               + 0.18 * np.sin(2 * np.pi * 0.5 * f * t) * np.exp(-t * 1.6))
        return _stereo(sig * env * 0.45)
    if name == "jet":
        n = int(p.get("dur", 2.6) * SR)
        t = np.arange(n) / SR
        u = t / t[-1]
        noise = rng.standard_normal(n)
        roar = _lp(noise, 1400.0) * np.sin(np.pi * u) ** 1.5
        hiss = _lp(noise - _lp(noise, 2500.0), 7000.0) * np.sin(np.pi * u) ** 3 * 0.35
        f = 2600.0 * (1.0 - 0.32 * np.tanh((u - 0.5) * 6))
        whine = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * u) ** 4 * 0.12
        m = roar / (np.max(np.abs(roar)) + 1e-9) + hiss + whine
        pan = np.clip((u - 0.5) * 1.8, -0.9, 0.9)
        return np.stack([m * np.minimum(1, 1 - pan), m * np.minimum(1, 1 + pan)], 1).astype(np.float32) * 0.6
    if name == "pop":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        crack = rng.standard_normal(n) * np.exp(-t * 180.0)
        crack = crack - _lp(crack, 900.0) * 0.6
        thump = np.sin(2 * np.pi * (70 + 40 * np.exp(-t * 30)) * t) * np.exp(-t * 14.0) * 0.9
        tail = _lp(rng.standard_normal(n), 3000.0) * np.exp(-t * 22.0) * 0.4
        m = crack * 1.4 + thump + tail
        return _stereo(m / (np.max(np.abs(m)) + 1e-9) * 0.95)
    if name == "squeak":
        n = int(p.get("dur", 0.5) * SR)
        t = np.arange(n) / SR
        u = t / t[-1]
        f = p.get("freq", 420.0) * (1.0 + 1.1 * u) * (1.0 + 0.05 * np.sin(2 * np.pi * 23 * t))
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
        tone = np.tanh(tone * 2.5) * (0.6 + 0.4 * _lp(rng.standard_normal(n), 60.0) / 1.5)
        env = np.sin(np.pi * u) ** 0.7
        return _stereo(tone * env * 0.25, p.get("pan", 0.0))
    if name == "whoosh":
        n = int(p.get("dur", 1.0) * SR)
        t = np.arange(n) / SR
        u = t / t[-1]
        noise = rng.standard_normal(n)
        lo = _lp(noise, 600.0)
        hi = _lp(noise, 4500.0) - lo
        m = (lo * (1 - u) + hi * u) * np.sin(np.pi * u) ** 2
        return _stereo(m / (np.max(np.abs(m)) + 1e-9) * 0.7, p.get("pan", 0.0))
    if name == "coin":
        f = p.get("freq", 2600.0)
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        sig = (np.sin(2 * np.pi * f * t) + 0.55 * np.sin(2 * np.pi * f * 2.76 * t + 1.0) * np.exp(-t * 5)
               + 0.3 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 9))
        sig = sig * np.minimum(1.0, t / 0.0012) * np.exp(-t * 8.0)
        return _stereo(sig * 0.4, p.get("pan", 0.0))
    if name == "shutter":
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        m = np.zeros(n)
        for t0, a in ((0.0, 1.0), (0.05, 0.65)):
            i = int(t0 * SR)
            tt = np.arange(n - i) / SR
            click = (rng.standard_normal(n - i) - _lp(rng.standard_normal(n - i), 1200.0)) * np.exp(-tt * 150.0)
            m[i:] += click * a
        return _stereo(m / (np.max(np.abs(m)) + 1e-9) * 0.6, p.get("pan", 0.0))
    if name == "notify":
        f1 = p.get("freq", 1568.0)
        n = int(0.42 * SR)
        t = np.arange(n) / SR
        sig = np.zeros(n)
        for t0, f in ((0.0, f1), (0.11, f1 * 4.0 / 3.0)):
            tt = np.clip(t - t0, 0.0, None)
            on = (t >= t0) * np.minimum(1.0, tt / 0.003) * np.exp(-tt * 18.0)
            sig += on * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt * 30.0))
        return _stereo(sig * 0.35, p.get("pan", 0.0))
    raise KeyError(f"unknown synth sound {name!r}")


def build(ep_dir):
    build_cache()
    spec = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    series = json.loads((ep_dir / "build" / "series.json").read_text(encoding="utf-8"))
    A = spec["audio"]
    ev = series.get("events", {})
    dur = spec["duration"]
    n = int(dur * SR)
    buf = np.zeros((n, 2), np.float32)
    rnd = random.Random(11)
    hits_buf = np.zeros_like(buf)

    cut = A.get("cut_at")

    def render_bed(b, offset):
        t0, t1 = b["from"], min(b["to"], dur)
        m = int((t1 - t0) * SR)
        if m <= 0:
            return
        t = t0 + np.arange(m) / SR
        rate = gear_rate(t) if b.get("rate") == "gears" else curve(b.get("rate", 1.0), t)
        sig = play(loopable(load(b["sound"])), m, rate, b.get("offset", offset))
        sig *= curve(b.get("gain", 1.0), t)[:, None].astype(np.float32)
        add(buf, sig, t0, b.get("pan", 0.0))

    for b in A.get("beds", []):
        if not (cut and b["from"] >= cut):
            render_bed(b, rnd.uniform(0, 5))

    srng = np.random.default_rng(23)
    for h in A.get("hits", []):
        x = synth(h["synth"], h, srng) if "synth" in h else load(h["sound"])
        rate = h.get("rate", 1.0)
        m = int(len(x) / rate)
        sig = play(x, m, rate, 0.0, loop=False) * h.get("gain", 1.0)
        t0 = h["at"]
        if h.get("align") == "peak":
            t0 -= peak_time(sig)
        elif h.get("align") == "end":
            t0 -= m / SR
        add(hits_buf, sig, t0, h.get("pan", 0.0))

    for s in A.get("scatter", []):
        times = sorted(ev.get(s["event"], []))
        last = -1e9
        for tt in times:
            if tt - last < s.get("window", 0.12) or tt >= A.get("cut_at", dur):
                continue
            last = tt
            x = load(rnd.choice(s["pool"]))
            rate = rnd.uniform(*s.get("rate", (1.0, 1.0)))
            sig = play(x, int(len(x) / rate), rate, 0.0, loop=False) * rnd.uniform(*s.get("gain", (0.3, 0.3)))
            add(buf, sig, tt + rnd.uniform(0, 0.03), rnd.uniform(-0.6, 0.6))

    tk = A.get("ticks")
    if tk:
        for k, tt in enumerate(ev.get(tk["event"], [])):
            if tk.get("until") is not None and tt >= tk["until"]:
                continue
            if tk.get("synth"):
                # a synthesized sound per event (e.g. an elevator chime or a rubber squeak), its pitch stepping by
                # the ratio `step` each time
                f = tk.get("freq", 700.0) * tk.get("step", 1.0) ** k
                add(buf, synth(tk["synth"], {"freq": f, "dur": tk.get("dur", 0.4)}, srng) * tk.get("gain", 0.3), tt)
                continue
            f = tk.get("freq", 1500) + tk.get("step", 0) * k
            tt_ = np.arange(int(0.07 * SR)) / SR
            blip = (np.sin(2 * np.pi * f * tt_) * np.exp(-tt_ * 55)).astype(np.float32) * tk.get("gain", 0.1)
            add(buf, np.stack([blip, blip], 1), tt)

    if cut:
        i = int(cut * SR)
        fade = np.linspace(1, 0, int(0.03 * SR), dtype=np.float32)[:, None]
        buf[i:i + len(fade)] *= fade
        buf[i + len(fade):] = 0
        for b in A.get("beds", []):   # beds that deliberately start after the cut (e.g. the loop back to the start)
            if b["from"] >= cut:
                render_bed(b, 0.0)
    buf += hits_buf

    rw = A.get("rewind")
    if rw:
        src0, src1 = rw["source"]
        m = int((rw["to"] - rw["from"]) * SR)
        p = np.arange(m) / m
        src_t = src1 - (src1 - src0) * p ** 1.6
        idx = np.clip((src_t * SR).astype(np.int64), 0, n - 1)
        rev = buf[idx].copy() * rw.get("gain", 0.25)
        add(buf, rev, rw["from"])

    story = buf[: int((cut or dur) * SR)]
    rms = float(np.sqrt(np.mean(story ** 2))) + 1e-9
    buf *= 10 ** (A.get("target_rms_db", -16.0) / 20) / rms
    buf = np.tanh(buf * 1.1) / 1.1
    peak = float(np.max(np.abs(buf)))
    if peak > 10 ** (-1.0 / 20):
        buf *= 10 ** (-1.0 / 20) / peak
    buf, before, after = master(buf)   # the channel's master loudness (config.TARGET_LUFS), well under the -1 dBFS cap
    out = ep_dir / "build" / "audio.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"  wrote {out} ({dur:.1f}s, story rms {20 * math.log10(rms):.1f} dB before gain; "
          f"{before['I']:.1f} -> {after['I']:.1f} LUFS, loudest 3 s {after['S_max']:.1f}, true peak {after['TP']:.1f} dBTP)")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
