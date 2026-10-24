"""Loudness as the platforms and the ear measure it (EBU R128 / LUFS, via ffmpeg's ebur128 filter).

Every mix is mastered to the channel's target, config.TARGET_LUFS (from studio.toml; -25.5 LUFS by default), and
qa.py fails anything more than 2 LU louder. Sound-effects-only videos with heavy booms feel louder than their
number: -15 LUFS (a normal level for music and speech) was reported as "insanely loud" on this pipeline's videos,
and -25.5 LUFS fixed it.
"""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def measure(buf, sr=config.SAMPLE_RATE):
    """buf: float array (n,) or (n, 2). Returns {"I": integrated LUFS, "S_max": loudest 3 s window (LUFS),
    "TP": true peak (dBTP)}."""
    x = np.asarray(buf, dtype="<f4")
    ch = 1 if x.ndim == 1 else x.shape[1]
    err = subprocess.run([config.require_ffmpeg(), "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(sr), "-ac", str(ch),
                          "-i", "-", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         input=np.ascontiguousarray(x).tobytes(), capture_output=True).stderr.decode("utf-8", "replace")
    summary = err[err.rfind("Summary:"):]
    s_vals = [float(v) for v in re.findall(r"\bS:\s*(-?[\d.]+)", err[:err.rfind("Summary:")])]
    return {"I": float(re.search(r"I:\s*(-?[\d.]+) LUFS", summary).group(1)),
            "S_max": max(s_vals) if s_vals else -120.0,
            "TP": float(re.search(r"Peak:\s*(-?[\d.]+|-inf)", summary).group(1).replace("-inf", "-120"))}


def master(buf, target=None, sr=config.SAMPLE_RATE, tp_limit=None):
    """Scale the finished mix so its integrated loudness is the channel target. Returns (buf, before, after).

    At a loud target the scaled peaks can pass qa.py's true-peak limit; then they are soft-limited (tanh, which
    leaves everything below the ceiling almost untouched) and the level is brought back to the target. At the
    default quiet target this never kicks in."""
    target = config.TARGET_LUFS if target is None else target
    tp_limit = config.MAX_TRUE_PEAK - 0.5 if tp_limit is None else tp_limit
    before = measure(buf, sr)
    buf = buf * np.float32(10 ** ((target - before["I"]) / 20))
    after = measure(buf, sr)
    for _ in range(4):
        if after["TP"] <= tp_limit:
            break
        ceiling = np.float32(10 ** ((tp_limit - 0.5) / 20))
        buf = (np.tanh(buf / ceiling) * ceiling).astype(np.float32)
        level = measure(buf, sr)
        buf = buf * np.float32(10 ** ((target - level["I"]) / 20))
        after = measure(buf, sr)
    return buf, before, after
