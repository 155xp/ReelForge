"""AgentCut: ReelForge's optional headless editing workflow, powered by HyperFrames."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths as P
from . import settings, tools

VERSION = "0.8.214"
PACKAGE = P.ROOT / "extras" / "agentcut"
EDIT_TOOLS = {"lint", "check", "validate", "info", "timeline", "snapshot", "inspect", "compositions", "docs", "history"}


def install_root() -> Path:
    return P.TOOLS / "agentcut"


def runtime() -> str:
    node = os.environ.get("REELFORGE_NODE") or shutil.which("node")
    if not node:
        raise ValueError("AgentCut needs Node.js 22+ and npm: https://nodejs.org/en/download")
    result = subprocess.run([node, "--version"], capture_output=True, text=True, check=True, timeout=30)
    if int(result.stdout.strip().lstrip("v").split(".")[0]) < 22:
        raise ValueError("AgentCut needs Node.js 22 or newer; set REELFORGE_NODE to its executable")
    return node


def executable() -> Path:
    package = install_root() / "node_modules" / "hyperframes"
    script = package / "bin" / "hyperframes.mjs"
    if not script.is_file():
        raise ValueError("AgentCut is optional and is not installed. Run: reelforge agentcut install")
    if json.loads((package / "package.json").read_text(encoding="utf-8"))["version"] != VERSION:
        raise ValueError("AgentCut's HyperFrames version differs from the lock; run reelforge agentcut install")
    return script


def environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update(HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_UPDATE_CHECK="1")
    ffmpeg = tools.find_ffmpeg()
    if ffmpeg:
        env.update(HYPERFRAMES_FFMPEG_PATH=ffmpeg, HYPERFRAMES_FFPROBE_PATH=tools.ffprobe_for(ffmpeg))
    return env


def invoke(*args: str | Path, capture: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run([runtime(), str(executable()), *map(str, args)],
                            env=environment(), capture_output=capture, text=True,
                            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError(f"HyperFrames {' '.join(map(str, args))} failed:\n"
                         f"{(result.stderr or '')[-4000:]}\n{(result.stdout or '')[-4000:]}")
    return result


def call(*args: str | Path) -> dict:
    result = invoke(*args, "--json")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise ValueError(f"HyperFrames returned invalid JSON: {result.stdout[-2000:]}") from None


def install() -> dict:
    node = runtime()
    npm = os.environ.get("REELFORGE_NPM") or shutil.which("npm.cmd" if P.WINDOWS else "npm")
    if not npm:
        raise ValueError("npm is required to install the optional editor")
    target = install_root()
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(PACKAGE / name, target / name)
    env = environment()
    env["PATH"] = str(Path(node).resolve().parent) + os.pathsep + env.get("PATH", "")
    # npm ci verifies every dependency against the committed lockfile's integrity hashes.
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=target, env=env, check=True,
                   stdin=subprocess.DEVNULL, stdout=sys.stderr)
    invoke("browser", "ensure", capture=False)
    return {"installed": True, "engine": "HyperFrames", "version": VERSION, "path": str(target)}


def schema() -> dict:
    return {
        "engine": "HyperFrames", "version": VERSION, "format": "HTML composition at EPISODE/edit/index.html",
        "root_attributes": {"data-composition-id": "main", "data-width": 1080, "data-height": 1920,
                            "data-fps": 30, "data-duration": "must equal episode.json render_until"},
        "clips": "Timed HTML elements: id, class=clip, data-start, data-duration, data-track-index.",
        "media": "Local assets in edit/media/. Video: muted or data-has-audio=true. Audio: explicit id.",
        "trims_and_speed": "data-media-start (source seconds), data-playback-rate; audio gain: data-volume.",
        "animation": "Paused GSAP timeline registered as window.__timelines.main; use lib/gsap.min.js.",
        "docs": "https://github.com/heygen-com/hyperframes/tree/main/skills/hyperframes",
        "commands": "agentcut tool COMMAND ... runs the pinned CLI's local editing/inspection commands.",
    }


def instructions() -> dict:
    return {
        "name": "AgentCut", "engine": "HyperFrames", "headless": True,
        "trigger": "open agentcut and make a video about <topic>", "guide": "docs/AGENTCUT.md",
        "workflow": [
            "Read the channel brief, AGENTS.md and docs/AGENTCUT.md; use the channel's rules.",
            "Run reelforge agentcut new SLUG --topic TEXT.",
            "Author edit/index.html using local media and timed clips; record sources and claims in facts.md.",
            "Use agentcut schema and agentcut tool docs for the engine's composition/editing instructions.",
            "Validate EPISODE, then render EPISODE; inspect the preview stills.",
            "Run pipeline/make_episode.py EPISODE --steps post; inspect QA, pictures, sound and facts.",
            "Write build/qa/review.md; after approval run --steps ship. The user posts manually.",
        ],
    }


def prepare(ep: Path) -> Path:
    edit = ep / "edit"
    if not (edit / "index.html").is_file():
        raise ValueError(f"Missing {edit / 'index.html'}")
    executable()
    dest = edit / "lib" / "gsap.min.js"
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(install_root() / "node_modules" / "gsap" / "dist" / "gsap.min.js", dest)
    return edit


def validate_episode(ep: Path) -> dict:
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    if spec.get("backend", "blender") != "agentcut":
        raise ValueError("This episode uses Blender; start one with new-episode SLUG --backend agentcut")
    for name in ("fps", "duration", "render_until"):
        value = spec[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"episode.json {name} must be a positive finite number")
    if spec["fps"] != 30 or spec["render_until"] > spec["duration"]:
        raise ValueError("AgentCut episodes must use 30 fps and render_until <= duration")
    for name in ("duration", "render_until"):
        if abs(spec[name] * 30 - round(spec[name] * 30)) > 1e-6:
            raise ValueError(f"{name} must align to a frame at 30 fps")
    edit = prepare(ep)
    call("lint", edit)
    result = call("info", edit)
    if (result["width"], result["height"]) != (1080, 1920):
        raise ValueError("The HyperFrames composition must be 1080x1920")
    duration = result["duration"]
    if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration):
        raise ValueError("HyperFrames returned an invalid composition duration")
    if abs(duration - spec["render_until"]) > 0.0001:
        raise ValueError("Composition duration must match episode.json render_until")
    return {**result, "frames": round(spec["render_until"] * spec["fps"])}


def starter(ep: Path, ep_id: str, s: dict) -> None:
    from . import jsonfmt

    duration = round(float(s["video"]["min_seconds"]) * 30) / 30
    spec = {
        "id": ep_id, "backend": "agentcut", "title": "WRITE THE HOOK LINE HERE",
        "series": s["format"]["series"], "fps": 30, "duration": duration,
        "render_until": duration, "lines": [], "audio": {"mixer": "agentcut"},
        "title_card": {"start": 0, "end": 2, "scrim": 0.7},
        "cta": {"start": duration - 2.4, "end": duration - 0.5, "text": s["video"]["cta"], "sub": ""},
        "cover": {"time": 0, "kicker": "WRITE THE", "keyword": "COVER", "tail": ""},
        "hashtags": settings.tag_list(s["captions"]["default_tags"])[:s["captions"]["max_hashtags"]],
    }
    ep.mkdir()
    (ep / "edit" / "media").mkdir(parents=True)
    jsonfmt.write(ep / "episode.json", spec)
    template = (P.TEMPLATES / "agentcut.html").read_text(encoding="utf-8")
    (ep / "edit" / "index.html").write_text(template.replace("__DURATION__", str(duration)), encoding="utf-8")
    facts = (P.TEMPLATES / "facts.md").read_text(encoding="utf-8").replace("{id}", ep_id)
    (ep / "facts.md").write_text(facts, encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv or argv == ["help"]:
        print(json.dumps(instructions(), indent=2))
        return 0
    ap = argparse.ArgumentParser(prog="reelforge agentcut", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("install", "status", "doctor", "schema"):
        sub.add_parser(name)
    new = sub.add_parser("new")
    new.add_argument("slug")
    new.add_argument("--topic", default="")
    sub.add_parser("inspect").add_argument("media", type=Path)
    sub.add_parser("tool").add_argument("args", nargs=argparse.REMAINDER)
    for name in ("validate", "render"):
        sub.add_parser(name).add_argument("episode", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.command == "new":
            from .__main__ import new_episode
            return new_episode([args.slug, "--backend", "agentcut", "--topic", args.topic])
        if args.command == "schema":
            result = schema()
        elif args.command == "install":
            result = install()
        elif args.command == "status":
            result = {"installed": (install_root() / "node_modules" / "hyperframes" / "package.json").is_file(),
                      "engine": "HyperFrames", "version": VERSION, "path": str(install_root())}
        elif args.command == "doctor":
            result = call("doctor")
            # Upstream's overall flag also includes optional voice/music models and Docker.
            required = {"Node.js", "FFmpeg", "FFprobe", "Chrome"}
            checks = {c["name"]: c.get("ok", False) for c in result.get("checks", [])}
            result = {**result, "engine_ok": result.get("ok"),
                      "ok": all(checks.get(name, False) for name in required),
                      "required_checks": sorted(required)}
            print(json.dumps(result, indent=2))
            return 0 if result.get("ok") else 1
        elif args.command == "inspect":
            ffmpeg = tools.find_ffmpeg()
            if not ffmpeg:
                raise ValueError("ffmpeg is missing; run setup or set STUDIO_FFMPEG")
            probed = subprocess.run([tools.ffprobe_for(ffmpeg), "-v", "error", "-show_streams", "-show_format",
                                     "-of", "json", str(args.media.resolve())], check=True, capture_output=True,
                                    text=True, timeout=60)
            result = json.loads(probed.stdout)
        elif args.command == "tool":
            if not args.args or args.args[0] not in EDIT_TOOLS:
                raise ValueError(f"Local editing tools: {', '.join(sorted(EDIT_TOOLS))}")
            invoke(*args.args, capture=False)
            return 0
        elif args.command == "validate":
            result = validate_episode(args.episode.resolve())
        else:
            ep = args.episode.resolve()
            return subprocess.run([sys.executable, str(P.ROOT / "pipeline" / "make_episode.py"), str(ep),
                                   "--steps", "build,stills,render"]).returncode
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": str(e)}))
        return 1
