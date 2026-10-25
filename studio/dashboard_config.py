"""Writes the dashboard's settings (dashboard/config.toml) from your studio settings: your handles, platforms, hashtags and folders.

It starts from dashboard/config.example.toml (so its comments stay) and only changes the keys it knows about. Values
you set by hand in dashboard/config.toml that onboarding doesn't manage are kept.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from . import paths as P
from . import settings as S

KEY = re.compile(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$")
SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*(#.*)?$")


def _comment_part(rest: str) -> str:
    """The trailing '   # comment' of a TOML value (a '#' inside a string isn't a comment), or ''."""
    quote = None
    i = 0
    while i < len(rest):
        c = rest[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            j = i
            while j > 0 and rest[j - 1] in " \t":
                j -= 1
            return rest[j:]
        i += 1
    return ""


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def set_keys(text: str, values: dict[str, dict]) -> str:
    """values = {"": {top-level key: value}, "section": {key: value}}. Replaces existing keys in place (keeping
    their comments) and adds missing ones at the end of their section (adding the section if needed)."""
    lines = text.splitlines()
    pending = {sec: dict(kv) for sec, kv in values.items()}
    out: list[str] = []
    section = ""

    def flush(sec: str):
        for k, v in pending.get(sec, {}).items():
            out.append(f"{k} = {_value(v)}")
        pending[sec] = {}

    for line in lines:
        m = SECTION.match(line)
        if m:
            blanks = 0
            while out and not out[-1].strip():          # missing keys go above the blank lines
                out.pop()
                blanks += 1
            flush(section)
            out.extend([""] * blanks)
            section = m.group(1).strip()
            out.append(line)
            continue
        k = KEY.match(line)
        if k and k.group(2) in pending.get(section, {}):
            v = pending[section].pop(k.group(2))
            out.append(f"{k.group(1)}{k.group(2)}{k.group(3)}{_value(v)}{_comment_part(k.group(4))}")
            continue
        out.append(line)
    flush(section)
    for sec, kv in pending.items():
        if kv:
            out.append("")
            out.append(f"[{sec}]")
            for k, v in kv.items():
                out.append(f"{k} = {_value(v)}")
    return "\n".join(out) + "\n"


def wanted(s: dict) -> dict[str, dict]:
    """The dashboard settings onboarding manages."""
    tags = " ".join("#" + t for t in S.tag_list(s["captions"]["default_tags"])[: s["captions"]["max_hashtags"]])
    v: dict[str, dict] = {"": {"default_tags": tags, "episodes_dir": "../episodes",
                               "completed_dir": "../completed videos"}}
    for p in S.PLATFORMS:
        v[p] = {"handle": s["platforms"]["handles"].get(p, "") if p in s["platforms"]["enabled"] else ""}
    return v


def write(s: dict) -> list[Path]:
    example = P.DASHBOARD / "config.example.toml"
    target = P.DASHBOARD / "config.toml"
    if not example.exists() and not target.exists():
        return []
    base = target.read_text(encoding="utf-8") if target.exists() else example.read_text(encoding="utf-8")
    known = _known_keys(example) if example.exists() else None
    values = wanted(s)
    if known is not None:          # only touch keys this version of the dashboard understands
        values = {sec: {k: v for k, v in kv.items() if k in known.get(sec, set())} for sec, kv in values.items()}
    text = set_keys(base, values)
    tomllib.loads(text)            # never write a config the dashboard can't read
    target.write_text(text, encoding="utf-8", newline="\n")
    return [target]


def _known_keys(example: Path) -> dict[str, set]:
    data = tomllib.loads(example.read_text(encoding="utf-8"))
    known = {"": {k for k, v in data.items() if not isinstance(v, dict)}}
    for k, v in data.items():
        if isinstance(v, dict):
            known[k] = set(v)
    return known
