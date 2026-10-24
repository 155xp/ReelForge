"""Procedural sound design for an episode, no samples needed (the render-distance example uses it).

Layers: city ambience that fades as the world unloads, digital ticks/thumps for every unload event,
a tension drone, scripted hits (sky unload, heartbeat), a glitch-stutter climax, and an end-card pad.
Reads episode.json + build/series.json, writes build/audio.wav (48 kHz stereo).
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

SR = config.SAMPLE_RATE


def _freqs(n):
    return np.fft.rfftfreq(n, 1.0 / SR)


def lowpass(x, cutoff, order=2):
    f = _freqs(len(x))
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (f / cutoff) ** (2 * order)), n=len(x))


def highpass(x, cutoff, order=2):
    f = np.maximum(_freqs(len(x)), 1e-3)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (cutoff / f) ** (2 * order)), n=len(x))


def norm(x):
    p = np.max(np.abs(x))
    return x / p if p > 0 else x


def env_from_series(values, fps, n):
    t_frames = np.arange(len(values)) / fps
    return np.interp(np.arange(n) / SR, t_frames, values)


def add(buf, sig, t0, pan=0.0, gain=1.0):
    """Mix a mono signal into the stereo buffer at time t0 with equal-power pan (-1..1)."""
    i0 = int(t0 * SR)
    if i0 >= buf.shape[0] or i0 + len(sig) <= 0:
        return
    s = sig[max(0, -i0):]
    i0 = max(i0, 0)
    s = s[:buf.shape[0] - i0]
    a = (pan + 1) * math.pi / 4
    buf[i0:i0 + len(s), 0] += s * math.cos(a) * gain
    buf[i0:i0 + len(s), 1] += s * math.sin(a) * gain


def tone(freq, dur, decay, phase=0.0):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * freq * t + phase) * np.exp(-t * decay)


def sweep(f0, f1, dur, decay):
    t = np.arange(int(dur * SR)) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)


def crush(x, bits=4, hold=1):
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    if hold > 1:
        y = np.repeat(y[::hold], hold)[:len(x)]
    return y


def build(ep_dir):
    spec = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    series = json.loads((ep_dir / "build" / "series.json").read_text(encoding="utf-8"))
    A = spec.get("audio", {})
    fps = spec["fps"]
    dur = spec["duration"]
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    prng = random.Random(7)
    buf = np.zeros((n, 2))
    t = np.arange(n) / SR

    rd = env_from_series(series["rd_m"], fps, n)
    city_gain = np.clip(rd / 150.0, 0, 1) ** 0.6
    t_you = A.get("you", spec.get("render_until", dur))
    city_gain[t >= t_you] = 0

    # ---- city ambience
    brown = np.cumsum(rng.standard_normal(n))
    traffic = norm(lowpass(highpass(brown, 25), 350)) * 0.75
    air = norm(lowpass(highpass(rng.standard_normal(n), 400), 4000)) * 0.08
    amb = (traffic + air) * city_gain
    buf[:, 0] += amb
    buf[:, 1] += np.roll(amb, 240)

    # passing cars: filtered-noise swells that pan across
    tc = 1.5
    while tc < 44:
        d = prng.uniform(2.0, 3.5)
        m = int(d * SR)
        s = norm(lowpass(highpass(rng.standard_normal(m), 150), 1400)) * np.hanning(m) * 0.25
        g = city_gain[min(int(tc * SR), n - 1)]
        side = prng.choice((-1, 1))
        half = m // 2
        add(buf, s[:half], tc, pan=-0.7 * side, gain=g)
        add(buf, s[half:], tc + half / SR, pan=0.7 * side, gain=g)
        tc += prng.uniform(2.5, 6.0)

    # birds early on
    tb = 0.8
    while tb < 30:
        for _ in range(prng.randint(2, 4)):
            f0 = prng.uniform(3000, 5200)
            ch = sweep(f0, f0 * prng.uniform(1.15, 1.4), prng.uniform(0.06, 0.11), 18) * 0.03
            add(buf, ch, tb, pan=prng.uniform(-0.8, 0.8), gain=city_gain[int(tb * SR)])
            tb += prng.uniform(0.09, 0.16)
        tb += prng.uniform(1.0, 3.5)

    # ---- unload events: digital ticks, low thumps for big objects
    last_thump = -1.0
    for f, kind, size in series["events"]:
        te = (f - 1) / fps + prng.uniform(0, 1 / fps)
        if te >= t_you:
            continue
        pan = prng.uniform(-0.7, 0.7)
        if kind == "unload":
            tick = crush(tone(prng.uniform(1300, 3400), 0.05, 95), bits=4)
            add(buf, tick, te, pan=pan, gain=0.016)
            if size > 60 and te - last_thump > 0.3:
                thump = sweep(85, 38, 0.9, 4.5) * 0.16
                thump += lowpass(rng.standard_normal(len(thump)), 300) * np.exp(-np.arange(len(thump)) / SR * 7) * 0.08
                add(buf, thump, te, pan=pan * 0.3)
                last_thump = te
        else:
            add(buf, crush(tone(prng.uniform(3000, 4200), 0.035, 120), bits=4), te, pan=pan, gain=0.012)

    # ---- tension drone (from the first drop to the climax)
    keys = spec["effect"].get("keys", [[0, 1], [0, 1]])
    drop_t = next((a[0] for a, b in zip(keys, keys[1:]) if b[1] < a[1]), 0.0)  # when the curve starts falling
    dg =np.clip((t - drop_t) / (t_you - drop_t), 0, 1)
    drone = sum(np.sin(2 * np.pi * fr * t + ph) for fr, ph in ((55.0, 0), (55.35, 1), (82.4, 2), (110.2, 3))) / 4
    drone *= (0.04 + 0.12 * dg) * (t >= drop_t) * (t < t_you)
    buf[:, 0] += drone
    buf[:, 1] += drone

    # ---- sky unload hit + the dead air after it
    if "sky_unload" in A:
        ts = A["sky_unload"]
        hit = sweep(320, 32, 1.6, 2.2) * 0.45
        hit += lowpass(rng.standard_normal(len(hit)), 700) * np.exp(-np.arange(len(hit)) / SR * 3) * 0.18
        add(buf, hit, ts)
        whine_g = np.clip((t - ts) / (t_you - ts), 0, 1) * (t >= ts) * (t < t_you)
        whine = np.sin(2 * np.pi * 7200 * t) * 0.012 * whine_g + np.sin(2 * np.pi * 60 * t) * 0.02 * (whine_g > 0)
        buf[:, 0] += whine
        buf[:, 1] += whine

    # ---- heartbeat
    if "heartbeat" in A:
        h0, h1 = A["heartbeat"]
        tb = h0
        while tb < h1:
            prog = (tb - h0) / (h1 - h0)
            for k, g in ((0, 1.0), (0.17, 0.7)):
                beat = lowpass(sweep(70, 40, 0.25, 14), 160) * 0.30 * g * (0.6 + 0.4 * prog)
                add(buf, beat, tb + k)
            tb += 0.95 - 0.35 * prog

    # ---- the climax: stutter + bitcrush + digital bursts, then a hard cut
    b0, b1 = spec.get("blackout", [t_you + 3.5, t_you + 5])
    if t_you < b0:
        src = buf[int((t_you - 2.0) * SR):int(t_you * SR)].copy()
        pos = t_you
        while pos < b0:
            prog = (pos - t_you) / (b0 - t_you)
            g = int(prng.uniform(0.04, 0.13) * SR)
            st = prng.randrange(0, len(src) - g)
            grain = src[st:st + g]
            for _ in range(prng.randint(2, 5)):
                if pos >= b0:
                    break
                crushed = np.stack([crush(grain[:, c] * 2.5, bits=3, hold=8 + int(prog * 24)) for c in (0, 1)], 1)
                i0 = int(pos * SR)
                seg = crushed[:max(0, min(len(crushed), int(b0 * SR) - i0))]
                buf[i0:i0 + len(seg)] = seg * (0.5 + 0.3 * prog)
                pos += len(grain) / SR
            if prng.random() < 0.6:
                sq = np.sign(np.sin(2 * np.pi * prng.uniform(180, 2200) * np.arange(int(0.06 * SR)) / SR)) * 0.22
                add(buf, sq, pos, pan=prng.uniform(-1, 1))
        buf[int(b0 * SR):] = 0.0

    # ---- end card pad
    ec = spec.get("end_card")
    if ec:
        te = ec["start"]
        m = n - int(te * SR)
        tt = np.arange(m) / SR
        pad = sum(np.sin(2 * np.pi * fr * tt) for fr in (110.0, 164.8, 220.0, 110.4)) / 4
        envp = np.minimum(1, tt / 2.0) * np.minimum(1, (tt[::-1]) / 1.5)
        add(buf, pad * envp * 0.12, te)

    # ---- master: bring the story section to a target loudness, then soft-limit and cap peaks at -1 dBFS
    story = buf[: int(t_you * SR)]
    rms = np.sqrt(np.mean(story ** 2)) + 1e-9
    buf *= 10 ** (A.get("target_rms_db", -17.0) / 20) / rms
    buf = np.tanh(buf * 1.2) / 1.2
    peak = np.max(np.abs(buf))
    if peak > 10 ** (-1.0 / 20):
        buf *= 10 ** (-1.0 / 20) / peak
    buf, _before, after = master(buf)   # the channel's master loudness (config.TARGET_LUFS)
    out = ep_dir / "build" / "audio.wav"
    pcm = (np.clip(buf, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"  wrote {out} ({dur:.1f}s, {after['I']:.1f} LUFS, true peak {after['TP']:.1f} dBTP)")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
