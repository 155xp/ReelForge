"""Content-bound QA/review receipts. No renderer or optional runtime is needed to read them."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import profiles, settings


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(ep: Path, spec: dict | None = None, channel_settings: dict | None = None) -> dict:
    """Hash every delivered artifact and the inputs whose changes require another review.

    Missing optional outputs are recorded too: adding/removing a cover or platform caption changes the receipt.
    Build caches and review files are excluded, so cleaning retained frames does not revoke a completed review.
    """
    spec = spec if spec is not None else json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    s = channel_settings if channel_settings is not None else settings.load(profiles.of(ep).settings)
    final = ep / "final"
    names = {f"{spec['id']}.mp4", "cover.jpg", "caption.txt"}
    names.update(p.name for p in final.glob("caption_*.txt"))
    outputs = {name: file_digest(final / name) if (final / name).is_file() else None for name in sorted(names)}
    inputs = {"episode": spec,
              "settings": {k: s[k] for k in ("channel", "format", "video", "sound", "captions")},
              "platforms": s["platforms"]["enabled"]}
    # Facts and other authored episode inputs are part of what the reviewer has checked. Symlinked inputs are
    # hashed by content; unsupported directory arrangements must not silently disappear from the receipt.
    authored = {}
    for path in sorted(ep.iterdir()):
        if path.name in ("build", "final", "edit", "episode.json"):
            continue
        if path.is_file():
            authored[path.name] = file_digest(path)
        elif path.is_symlink():
            raise ValueError(f"Unsupported review input symlink: {path}; keep authored notes as local files")
    inputs["authored"] = authored
    if spec.get("backend", "blender") == "agentcut":
        from .agentcut_sources import fingerprint as source_fingerprint
        inputs["source"] = source_fingerprint(ep, spec)
    else:
        scene = ep / "build" / "scene.blend"
        inputs["scene"] = file_digest(scene) if scene.is_file() else None
    return {"schema": 1, "outputs": outputs, "inputs": inputs}


def fingerprint(receipt: dict) -> str:
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def qa_matches(report: dict, current: dict) -> bool:
    return bool(report.get("pass")) and report.get("review_snapshot") == current and \
        report.get("review_fingerprint") == fingerprint(current)


def review_matches(path: Path, digest: str) -> bool:
    """Require an explicit receipt in the human-authored review, never attach a stale APPROVED automatically."""
    if not path.is_file():
        return False
    matches = re.findall(r"^Review-SHA256:\s*([0-9a-f]{64})\s*$",
                         path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
    return bool(matches) and matches[-1] == digest
