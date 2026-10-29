"""The episode pipeline: one episodes/<id>/episode.json -> a finished, checked 9:16 video in ReelForge's Publish tab.

  python pipeline/make_episode.py episodes/<id> --steps build,stills --stills 1,15,31
  python pipeline/make_episode.py episodes/<id> --steps render        (20-40 min; resumable)
  python pipeline/make_episode.py episodes/<id> --steps post          (audio, video, cover, captions, QA)
  python pipeline/make_episode.py episodes/<id> --steps ship          (deliver, clean, check the Publish tab)

Steps: build (Blender scene from episode.json) -> stills (preview frames) -> render (all frames, resumable)
       -> post (= audio, video, cover, caption, qa) -> your own review in build/qa/review.md
       -> ship (= deliver: copy to "completed videos/" only if QA passed; clean: delete render frames;
                 check: confirm ReelForge's Publish tab lists the video with the right caption and hashtags).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from studio import settings  # noqa: E402

ALL_STEPS = ["build", "stills", "render", "audio", "video", "cover", "caption", "qa", "deliver", "clean", "check"]
ALIASES = {"post": ["audio", "video", "cover", "caption", "qa"],     # then review build/qa/ before shipping
           "ship": ["deliver", "clean", "check"],
           "all": ALL_STEPS}
NEEDS_BLENDER = {"build", "stills", "render"}
NEEDS_FFMPEG = {"audio", "video", "cover", "qa"}


def run(cmd, log=None):
    print(">", " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd), flush=True)
    t0 = time.time()
    try:
        if log:
            with open(log, "w", encoding="utf-8", errors="replace") as fh:
                subprocess.run([str(c) for c in cmd], check=True, stdout=fh, stderr=subprocess.STDOUT)
        else:
            subprocess.run([str(c) for c in cmd], check=True)
    except subprocess.CalledProcessError as e:
        hint = f" (see {log})" if log else ""
        raise SystemExit(f"step failed with exit code {e.returncode}{hint}") from None
    print(f"  done in {time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episode", type=Path)
    ap.add_argument("--steps", default="all")
    ap.add_argument("--stills", default="", help="comma-separated seconds for preview stills")
    args = ap.parse_args()

    ep = args.episode.resolve()
    if not (ep / "episode.json").exists():
        raise SystemExit(f"{ep / 'episode.json'} not found")
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    backend = spec.get("backend", "blender")
    if backend not in ("blender", "agentcut"):
        raise SystemExit(f"unknown episode backend {backend!r}; choose blender or agentcut")
    build = ep / "build"
    final = ep / "final"
    build.mkdir(exist_ok=True)
    final.mkdir(exist_ok=True)
    fps = spec["fps"]

    steps = []
    for s in args.steps.split(","):
        s = s.strip()
        if s not in ALIASES and s not in ALL_STEPS:
            raise SystemExit(f"unknown step {s!r}; steps: {', '.join(ALL_STEPS)} (or post, ship, all)")
        steps += ALIASES.get(s, [s])
    if backend == "blender" and NEEDS_BLENDER & set(steps):
        config.require_blender()
    if NEEDS_FFMPEG & set(steps) or backend == "agentcut" and {"stills", "render"} & set(steps):
        config.require_ffmpeg()

    if backend == "agentcut":
        from agentcut import Edit
        edit = Edit(ep, spec)
        if "build" in steps:
            edit.validate()
        if "stills" in steps:
            secs = [float(s) for s in args.stills.split(",") if s] or spec.get("preview_times") or [
                round(spec["render_until"] * i / 10, 3) for i in range(10)]
            edit.stills(secs)
        if "render" in steps:
            edit.frames()
        if {"audio", "video", "cover"} & set(steps):
            edit.require_render()
        if "deliver" in steps:
            edit.require_source()

    if backend == "blender" and "build" in steps:
        run([config.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
             "-P", config.PIPELINE / "blender" / "build_scene.py", "--", ep], log=build / "build.log")

    if backend == "blender" and "stills" in steps:
        secs = [float(s) for s in args.stills.split(",") if s] or spec.get("preview_times") or \
            [1, 15, 20, 26, 31, 38, 47, 55, 63, 67]
        frames = ",".join(str(int(round(s * fps)) + 1) for s in secs)
        (build / "stills").mkdir(exist_ok=True)
        run([config.BLENDER, "-b", build / "scene.blend", "-o", build / "stills" / "s_####", "-F", "JPEG",
             "-f", frames], log=build / "stills.log")

    if backend == "blender" and "render" in steps:
        run([config.BLENDER, "-b", build / "scene.blend", "-a"], log=build / "render.log")

    post = config.PIPELINE / "post"
    if "audio" in steps:
        mixer_type = spec.get("audio", {}).get("mixer")
        mixer = {"samples": "audio_mix.py", "agentcut": "agentcut_audio.py"}.get(mixer_type, "audio.py")
        run([sys.executable, "-I", post / mixer, ep])
    if "video" in steps:
        if backend == "agentcut" and not (build / "audio.wav").is_file():
            raise ValueError("AgentCut audio is missing after rendering; run --steps audio,video or --steps post")
        run([sys.executable, post / "compose.py", ep, "--video"])
    if "cover" in steps:
        run([sys.executable, post / "compose.py", ep, "--cover"])
    if "caption" in steps:
        write_captions(spec, final)
    if "qa" in steps:
        run([sys.executable, config.PIPELINE / "qa.py", ep])
    if "deliver" in steps:
        deliver(spec, final, build)
    if "clean" in steps:
        clean(spec, build)
    if "check" in steps:
        check_publish(ep)


def completed_dir(spec):
    title = "".join(c for c in spec["title"] if c not in '<>:"/\\|?*').strip(" .")
    return config.COMPLETED / f"{spec['id']} - {title}"[:120].rstrip(" .")


def deliver(spec, final, build):
    """Copy the finished video, cover and captions to 'completed videos/<id> - <title>/', only if QA passed on
    this exact video file."""
    if spec.get("demo"):
        raise SystemExit("deliver: this is one of ReelForge's demos, so it can't ship: start your own episode with "
                         "reelforge new-episode and make the subject yours")
    video = final / f"{spec['id']}.mp4"
    if not video.exists():
        raise SystemExit(f"deliver: {video} not found, run the video step first")
    qa_file = build / "qa" / "qa.json"
    if not qa_file.exists():
        raise SystemExit("deliver: no QA report, run --steps qa first")
    qa = json.loads(qa_file.read_text(encoding="utf-8"))
    st = video.stat()
    if not qa.get("pass") or qa.get("fingerprint") != f"{st.st_size}:{int(st.st_mtime)}":
        raise SystemExit("deliver: QA failed or is out of date for this video; fix it and rerun --steps qa")
    from studio.publish_check import review_approved
    if not review_approved(build / "qa" / "review.md"):
        raise SystemExit("deliver: write your own review first: build/qa/review.md (picture, sound, facts) "
                         "ending with the verdict APPROVED (or REJECTED: why)")
    dst = completed_dir(spec)
    dst.mkdir(parents=True, exist_ok=True)
    files = [video, final / "cover.jpg", final / "caption.txt", *sorted(final.glob("caption_*.txt"))]
    for f in files:
        if f.exists():
            shutil.copy2(f, dst / f.name)
    print(f"  delivered {sum(f.exists() for f in files)} files to {dst}")


def clean(spec, build):
    """Delete the bulky render frames/stills/previews once the video is safely in 'completed videos'."""
    copy = completed_dir(spec) / f"{spec['id']}.mp4"
    if not copy.exists():
        raise SystemExit("clean: the video isn't in 'completed videos' yet; deliver first")
    freed = 0
    for sub in ("frames", "stills", "preview"):
        d = build / sub
        if d.exists():
            freed += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d)
    print(f"  cleaned render files ({freed / 1e9:.2f} GB freed); scene.blend, series.json, audio and QA kept")


def check_publish(ep):
    """Confirm ReelForge's Publish tab will list this video, with the caption and hashtags the channel's rules give."""
    from studio import publish_check
    ok, report = publish_check.check(ep)
    print(report)
    if not ok:
        raise SystemExit("check: the video isn't ready in ReelForge's Publish tab (see above)")


def write_captions(spec, final):
    """Per-platform posts in the channel's format: the caption is one short hook line (the episode `title`).
    TikTok/Instagram: caption + hashtags; YouTube: caption as title, hashtags as description; X: caption (hashtags
    only if the channel allows them there). Rules (max hashtags, TikTok's first tag) come from studio.toml."""
    s = config.SETTINGS
    tags = settings.tag_list(spec.get("hashtags", []))
    n = config.MAX_HASHTAGS
    if len(tags) > n:
        raise SystemExit(f"caption: {len(tags)} hashtags in episode.json, the channel's maximum is {n}")
    first = config.TIKTOK_FIRST_TAG
    if "tiktok" in config.PLATFORMS and first and first.lower() not in (t.lower() for t in tags) and len(tags) >= n:
        raise SystemExit(f"caption: TikTok needs #{first} first and max {n} hashtags; drop one hashtag from "
                         "episode.json")
    hook = " ".join(spec["title"].split())
    if "#" in hook:
        raise SystemExit("caption: put hashtags in episode.json 'hashtags', not in the title")
    if len(hook) > 280:
        raise SystemExit(f"caption: the title is {len(hook)} characters, X allows 280")
    if len(hook) > config.TITLE_MAX_CHARS:
        print(f"  note: the title is {len(hook)} characters (the channel aims for {config.TITLE_MAX_CHARS} or fewer)")
    out = settings.post_texts(hook, tags, s)
    for f in final.glob("caption_*.txt"):            # platforms switched off since the last run
        if f.stem.split("_", 1)[1] not in out:
            f.unlink()
    for platform, text in out.items():
        (final / f"caption_{platform}.txt").write_text(text, encoding="utf-8")
    # The Publish tab reads final/caption.txt: caption, blank line, hashtags (TikTok's order, so the first tag leads).
    tag_line = " ".join("#" + t for t in settings.platform_tags("tiktok", tags, s))
    (final / "caption.txt").write_text(f"{hook}\n\n{tag_line}\n" if tag_line else f"{hook}\n", encoding="utf-8")
    print(f"  wrote captions for {', '.join(out)} (hook: {len(hook)} chars)")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error)) from None
