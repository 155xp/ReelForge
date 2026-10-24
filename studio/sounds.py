"""The sound library: assets/sfx/manifest.json lists every sound with its source and licence.

Kenney (CC0) and the kit's own synthesized sounds ship with the kit. Mixkit's licence lets you use its sounds in
your videos but not redistribute the files, so they are fetched from Mixkit on your computer (checked against the
manifest's checksums) the first time you run setup.
"""

from __future__ import annotations

import hashlib
import json

from . import net
from .paths import SFX

MIXKIT_LICENSE = "https://mixkit.co/license/#sfxFree"


def manifest() -> dict:
    return json.loads((SFX / "manifest.json").read_text(encoding="utf-8"))


def missing() -> list[tuple[str, dict]]:
    """Sounds whose file isn't on disk yet (and isn't already converted into the cache)."""
    out = []
    for name, meta in manifest()["sounds"].items():
        if not (SFX / meta["file"]).exists() and not (SFX / "_cache" / f"{name}.wav").exists():
            out.append((name, meta))
    return out


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_mixkit(log=lambda s: print(s, flush=True), progress=None) -> list[str]:
    """Download every missing Mixkit sound. Returns the names that failed. progress(text, done, total), if given,
    hears about each file instead of log."""
    m = manifest()
    url_t = m.get("_mixkit_url", "https://assets.mixkit.co/active_storage/sfx/{id}/{id}.{ext}")
    failed = []
    todo = [(n, meta) for n, meta in missing() if meta["source"] == "mixkit"]
    for k, (name, meta) in enumerate(todo, 1):
        dest = SFX / meta["file"]
        ext = dest.suffix.lstrip(".")
        url = url_t.format(id=meta["id"], ext=ext)
        try:
            data = net.fetch_bytes(url)
            if meta.get("sha256") and _sha256(data) != meta["sha256"]:
                raise RuntimeError("checksum mismatch (Mixkit may have changed the file)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if progress:
                progress(f"Downloading sound {k} of {len(todo)}", k, len(todo))
            else:
                log(f"  [{k}/{len(todo)}] {name} ({len(data) / 1e6:.1f} MB)")
        except Exception as e:  # network errors, 403s, checksum
            failed.append(name)
            if progress:
                progress(f"Sound {k} of {len(todo)} didn't download", k, len(todo))
            else:
                log(f"  [{k}/{len(todo)}] {name}: FAILED ({e})")
    return failed


def build_cache(log=print, quiet: bool = False) -> None:
    """Convert every sound to 48 kHz WAV (pipeline/post/sfx_cache.py), so mixing is fast."""
    import subprocess
    import sys

    from .paths import ROOT

    subprocess.run([sys.executable, "-I", str(ROOT / "pipeline" / "post" / "sfx_cache.py")], check=True,
                   capture_output=quiet)


def mixkit_count() -> int:
    return sum(1 for m in manifest()["sounds"].values() if m["source"] == "mixkit")
