"""Your studio's settings: my-studio/studio.toml (written by onboarding) laid over the defaults below.

The pipeline (captions, QA, loudness, video length) and the dashboard both read these, so one interview configures
everything. Edit studio.toml by hand if you like, or run onboarding again.
"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from pathlib import Path

from .paths import SETTINGS

PLATFORMS = ("tiktok", "youtube", "instagram", "x")
PLATFORM_NAMES = {"tiktok": "TikTok", "youtube": "YouTube Shorts", "instagram": "Instagram Reels", "x": "X"}
RECOMMENDED = ("tiktok", "youtube", "instagram")  # the three big short-video apps: onboarding ticks these to start

# Loudness choices offered by onboarding (integrated LUFS). Sound-effects-only videos with heavy booms feel much
# louder than their LUFS number suggests: -15 LUFS ("normal" for music and speech) was reported as far too loud on
# exactly this pipeline's videos, and -25.5 LUFS was what fixed it.
LOUDNESS = {
    "quiet": (-25.5, "Quiet: -25.5 LUFS, tested on this kit's sound-effects-only videos; easy on the ears"),
    "medium": (-20.0, "Medium: -20 LUFS"),
    "loud": (-15.0, "Loud: -15 LUFS, about as loud as most uploads (booms will hit hard)"),
}

DEFAULTS: dict = {
    "studio": {"kit_version": "", "created": "", "updated": ""},
    "channel": {
        "name": "My Channel",
        "creator": "",                 # what the AI calls you
        "about": "",
        "audience": "",
        "tone": [],
        "language": "English",
    },
    "format": {
        "template": "doubling",
        "series": "Doubling",
        "premise": "",
        "twist": "",
        "custom": "",
        "references": [],
        "subjects": [],
        "avoid": "",
        "episode_label": "Ep. {n}",
    },
    "video": {
        "fps": 30,
        "min_seconds": 61.0,           # TikTok's Creator Rewards only pays for videos over 1 minute
        "max_seconds": 75.0,
        "hud": True,                   # a big on-screen counter
        "loop": True,                  # end on the first frame so the video loops seamlessly
        "cta": "FOLLOW FOR MORE",
        "style": "cinematic",
        "style_notes": "",
        "voiceover": False,            # the pipeline tells the story in on-screen lines, no narration
    },
    "sound": {"loudness": "quiet", "target_lufs": -25.5},
    "captions": {
        "max_hashtags": 5,
        "tiktok_first_tag": "fyp",     # "" for none
        "hashtags_on_x": False,
        "title_max_chars": 80,
        "default_tags": ["fyp", "whatif", "simulation", "physics", "space"],
    },
    "platforms": {
        "enabled": list(PLATFORMS),
        "handles": {p: "" for p in PLATFORMS},
        "background_stats": True,      # an hourly job reads your stats while ReelForge is closed
    },
    "schedule": {"per_day": 2, "per_week": 14, "post_times": "8-11 am and 5-8 pm", "timezone": ""},
    "ai": {"assistant": "claude", "quality": "max", "ultracode": True},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path | None = None) -> dict:
    """Settings as a plain dict: the defaults with studio.toml laid over them (missing file = defaults)."""
    path = path or SETTINGS
    data: dict = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)
    s = _merge(DEFAULTS, data)
    s["platforms"]["enabled"] = [p for p in s["platforms"]["enabled"] if p in PLATFORMS] or list(PLATFORMS)
    s["captions"]["max_hashtags"] = max(0, int(s["captions"]["max_hashtags"]))
    s["captions"]["tiktok_first_tag"] = str(s["captions"]["tiktok_first_tag"]).lstrip("#").strip()
    return s


def onboarded(path: Path | None = None) -> bool:
    return (path or SETTINGS).exists()


# ---------------------------------------------------------------- caption rules (shared by the pipeline and the dashboard)

_HASHTAG = re.compile(r"(?<![\w&])#\w+")


def tag_list(tags) -> list[str]:
    """'#a b #A #c' or ['a', '#b'] -> ['a', 'b', 'c']: hashtags without '#', in order, repeats dropped."""
    words = tags if isinstance(tags, (list, tuple)) else str(tags).replace(",", " ").split()
    out, seen = [], set()
    for w in words:
        t = str(w).strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def platform_tags(platform: str, tags, s: dict) -> list[str]:
    """The hashtags a platform gets: at most max_hashtags; TikTok's first one forced; none on X unless allowed."""
    c = s["captions"]
    n = c["max_hashtags"]
    if platform == "x" and not c["hashtags_on_x"]:
        return []
    out = tag_list(tags)
    first = c["tiktok_first_tag"]
    if platform == "tiktok" and first:
        out = [first] + [t for t in out if t.lower() != first.lower()]
    return out[:n]


def strip_hashtags(text: str) -> str:
    return " ".join(_HASHTAG.sub(" ", text).split())


def post_texts(title: str, tags, s: dict) -> dict[str, str]:
    """Every enabled platform's post, in the format the channel uses:
    TikTok and Instagram: the hook line + hashtags. YouTube: the hook is the title, the hashtags the description
    (written as 'title, blank line, hashtags'). X: the hook (+ hashtags only if allowed)."""
    hook = strip_hashtags(" ".join(title.split()))
    tags = tag_list([*_HASHTAG.findall(title), *tag_list(tags)])
    out = {}
    for p in s["platforms"]["enabled"]:
        line = " ".join("#" + t for t in platform_tags(p, tags, s))
        if p == "youtube":
            out[p] = f"{hook}\n\n{line}\n" if line else f"{hook}\n"
        else:
            out[p] = f"{hook} {line}".strip() + "\n"
    return out


# ---------------------------------------------------------------- writing studio.toml (no extra dependency)

def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)   # a JSON string is a valid TOML basic string


def dump_toml(data: dict, comments: dict | None = None) -> str:
    """dict -> TOML text. Nested dicts become [tables]; `comments` maps 'table' or 'table.key' to a comment."""
    comments = comments or {}
    lines: list[str] = []

    def table(prefix: str, d: dict):
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        subs = {k: v for k, v in d.items() if isinstance(v, dict)}
        if prefix and scalars:
            if lines:
                lines.append("")
            if prefix in comments:
                lines.extend("# " + c for c in comments[prefix].splitlines())
            lines.append(f"[{prefix}]")
        for k, v in scalars.items():
            note = comments.get(f"{prefix}.{k}" if prefix else k)
            lines.append(f"{k} = {_toml_value(v)}" + (f"   # {note}" if note else ""))
        for k, v in subs.items():
            table(f"{prefix}.{k}" if prefix else k, v)

    table("", data)
    return "\n".join(lines) + "\n"
