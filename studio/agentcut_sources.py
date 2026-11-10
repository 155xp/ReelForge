"""Content identity and the supported, local-only AgentCut source tree.

Walk logical paths, including directory symlinks, rather than Path.rglob (which
silently omits linked directories). External assets must be linked/copied into
edit/ so their contents are included in the same identity.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

IGNORED = {".hyperframes", "node_modules", "renders"}
PLAYLISTS = {".m3u", ".m3u8", ".mpd", ".ffconcat", ".sdp", ".ism", ".ismc", ".f4m", ".pls"}
RESOURCES = {".html", ".htm", ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".webp",
             ".avif", ".svg", ".ico", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".mp3", ".wav",
             ".flac", ".ogg", ".oga", ".opus", ".aac", ".m4a", ".ttf", ".otf", ".woff", ".woff2"}
TEXT_SOURCES = {".html", ".htm", ".css", ".svg", ".js", ".mjs"}
CSP = ("default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
       "style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; "
       "frame-src 'self'; base-uri 'self'")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(edit: Path):
    """Yield logical files; fail closed on broken links, cycles and special files."""
    if not edit.is_dir():
        raise ValueError("AgentCut needs an edit/ source directory")

    def walk(folder, ancestors):
        try:
            resolved = folder.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError(f"Unsupported AgentCut source link: {folder}") from error
        if resolved in ancestors:
            raise ValueError(f"Cyclic AgentCut source directory: {folder}")
        for path in sorted(folder.iterdir(), key=lambda p: p.name):
            relative = path.relative_to(edit)
            if len(relative.parts) == 1 and path.name in IGNORED:
                continue
            if path.is_dir():
                yield from walk(path, ancestors | {resolved})
            elif path.is_file():
                yield path
            else:
                raise ValueError(f"Unsupported or broken AgentCut source: {relative}; use regular local files")

    yield from walk(edit, set())


def fingerprint(ep: Path, spec: dict) -> str:
    files = {path.relative_to(ep / "edit").as_posix(): file_hash(path)
             for path in source_files(ep / "edit")}
    payload = {"version": 2, "timing": {key: spec[key] for key in ("fps", "render_until")}, "files": files}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _reference(value: str, path: Path, edit: Path):
    value = value.strip()
    if not value or value.startswith("#"):
        return
    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"data", "blob"}:
        raise ValueError("AgentCut dependencies must be regular local files; save embedded resources inside edit/")
    if parsed.scheme or parsed.netloc or value.startswith(("/", "\\")):
        raise ValueError(f"AgentCut supports local media only: {path.relative_to(edit)} references {value!r}; "
                         "download the asset into edit/media/ first")
    relative = unquote(parsed.path).replace("\\", "/")
    # Resolve .. lexically, preserving symlinked media trees as logical sources.
    parts = list(path.relative_to(edit).parent.parts)
    for part in relative.split("/"):
        if part == "..":
            if not parts:
                raise ValueError(f"AgentCut source escapes edit/: {value!r}; copy or link it inside edit/")
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    if parts and parts[0] in IGNORED:
        raise ValueError(f"AgentCut source uses an untracked generated directory: {value!r}")
    if relative and Path(relative).suffix.lower() not in RESOURCES:
        raise ValueError(f"Unsupported AgentCut resource {value!r}; use self-contained local media, fonts, HTML, CSS or JavaScript")
    if relative and not (edit.joinpath(*parts)).is_file():
        raise ValueError(f"AgentCut local source is missing: {value!r} in {path.relative_to(edit)}")


class _References(HTMLParser):
    def __init__(self, path, edit):
        super().__init__(convert_charrefs=True)
        self.path, self.edit = path, edit
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.in_script = True
        for key, value in attrs:
            if value is None:
                continue
            if tag == "base":
                raise ValueError("AgentCut does not support <base>; use paths relative to edit/")
            if key in {"src", "poster", "data-src", "data-poster", "xlink:href", "data-composition-src",
                       "data-composition-file", "data-hf-inlined-src", "data-lazy-src", "data-lottie-src",
                       "data-thumbnail-url", "data-var-src"} or (key == "href" and tag != "a"):
                _reference(value, self.path, self.edit)
            if key == "srcset":
                # Avoid ambiguous commas inside embedded data URLs.
                if value.strip().startswith("data:"):
                    raise ValueError("AgentCut does not support data: srcset; use a local image")
                for item in value.split(","):
                    if not item.strip():
                        raise ValueError("AgentCut srcset must name a local image")
                    _reference(item.strip().split()[0], self.path, self.edit)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)


CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
CSS_IMPORT = re.compile(r"@import\s+['\"]([^'\"]+)['\"]", re.I)
NETWORK_API = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(|\bimport\s*\(")
JS_IMPORT = re.compile(r"(?:\bfrom\s*|\bimport\s*)['\"]([^'\"]+)['\"]")
REMOTE_LITERAL = re.compile(r"['\"](?:https?:|ftp:|file:|//)[^'\"]*['\"]", re.I)


def validate_local_sources(edit: Path):
    """Reject unsupported dependency arrangements before any engine command.

Local scripts may animate existing elements. Network APIs, dynamic imports and
remote URL literals are unsupported; the render copy also enforces a browser
CSP so a dynamically constructed URL cannot load untracked remote content.
"""
    for path in source_files(edit):
        # FFmpeg resolves playlists outside the browser, where CSP cannot protect the render.
        # Reject their magic as well as extensions so renaming one to .mp4 cannot bypass this policy.
        with path.open("rb") as stream:
            header = stream.read(65536).lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
        playlist = (header.startswith((b"#EXTM3U", b"ffconcat version", b"[playlist]", b"v=0")) or
                    re.search(br"<(?:[a-zA-Z_]+:)?(?:MPD|SmoothStreamingMedia|smil)(?:\s|>)", header, re.I))
        if path.suffix.lower() in PLAYLISTS or playlist:
            raise ValueError(f"Unsupported AgentCut media playlist: {path.relative_to(edit)}; "
                             "export a self-contained local video/audio file first")
        if path.suffix.lower() not in TEXT_SOURCES:
            continue
        # This trusted dependency is copied from the pinned installation by prepare().
        if path.relative_to(edit).as_posix() == "lib/gsap.min.js":
            continue
        text = path.read_text(encoding="utf-8")
        script = text if path.suffix.lower() in {".js", ".mjs"} else ""
        if path.suffix.lower() in {".html", ".htm", ".svg"}:
            parser = _References(path, edit)
            parser.feed(text)
            script = "\n".join(parser.scripts)
        for match in CSS_URL.finditer(text):
            _reference(match.group(2), path, edit)
        for match in CSS_IMPORT.finditer(text):
            _reference(match.group(1), path, edit)
        for match in JS_IMPORT.finditer(script):
            _reference(match.group(1), path, edit)
        if NETWORK_API.search(script) or REMOTE_LITERAL.search(script):
            raise ValueError(f"AgentCut supports local media only: unsupported network/dynamic dependency in "
                             f"{path.relative_to(edit)}; save dependencies inside edit/ and reference them directly")


def snapshot(edit: Path, destination: Path):
    """Make a resolved, immutable-for-this-render copy with local browser policy."""
    validate_local_sources(edit)
    for path in source_files(edit):
        target = destination / path.relative_to(edit)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if path.suffix.lower() in {".html", ".htm"}:
            text = target.read_text(encoding="utf-8")
            policy = '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">'
            # Precede *all* authored markup. Looking for <head> with a regex could put
            # the policy inside a comment/script, or after an already-loaded resource.
            text = re.sub(r"^\s*<!doctype[^>]*>\s*", "", text, count=1, flags=re.I)
            text = "<!doctype html>\n" + policy + "\n" + text
            target.write_text(text, encoding="utf-8")
