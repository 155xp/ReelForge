"""JSON written the way episode.json files are easiest to read: one story line or cue per line, short things inline."""

from __future__ import annotations

import json

WIDTH = 118


def _inline(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))


def dumps(obj, indent: int = 0) -> str:
    pad = " " * indent
    inner = " " * (indent + 2)
    flat = _inline(obj)
    if not isinstance(obj, (dict, list)) or len(flat) + indent <= WIDTH and (
            isinstance(obj, list) and all(not isinstance(x, (dict, list)) or len(_inline(x)) < 40 for x in obj)
            or isinstance(obj, dict) and indent > 0):
        return flat
    if isinstance(obj, list):
        items = [inner + dumps(x, indent + 2) for x in obj]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 2).lstrip()}" for k, v in obj.items()]
    return "{\n" + ",\n".join(items) + "\n" + pad + "}"


def write(path, obj) -> None:
    from pathlib import Path

    Path(path).write_text(dumps(obj) + "\n", encoding="utf-8", newline="\n")
