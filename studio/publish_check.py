"""Is a finished episode ready in ReelForge's Publish tab?

The Publish tab lists every episodes/<id>/final/<id>.mp4 and fills the post from episode.json's `title` and the
hashtag line of final/caption.txt. This check runs the dashboard's own listing code when it can (so it sees exactly
what the tab will show), and otherwise the same rules directly, then prints what each platform's post will say.

  python -m studio publish-check episodes/<id>
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import settings as S
from . import paths as P
from . import profiles
from . import review as receipts
from .paths import ROOT

# The latest of these is the verdict. "NOT APPROVED" has to be tried before "APPROVED", and the words have to be
# whole, so a review that says DISAPPROVED or "not approved" is not an approval.
_VERDICT = re.compile(r"\b(NOT\s+APPROVED|APPROVED|REJECTED)\b")


def review_approved(review: Path, fingerprint: str | None = None) -> bool:
    """True if build/qa/review.md's latest verdict is APPROVED (a later REJECTED wins over an earlier APPROVED).

    Only the whole words count: DISAPPROVED is not an approval, and "NOT APPROVED" is a rejection."""
    if not review.exists():
        return False
    text = review.read_text(encoding="utf-8", errors="replace").upper()
    found = _VERDICT.findall(text)
    return bool(found) and found[-1] == "APPROVED" and \
        (fingerprint is None or receipts.review_matches(review, fingerprint))


def _dashboard_listing():
    """(find(cfg) -> [Path], meta(path, cfg) -> ({caption, tags}, warnings), cfg) from the dashboard itself, or
    None."""
    try:
        from dashboard import config as dash_config
        from dashboard import videos as dash_videos
        cfg = dash_config.load_config()
    except Exception:
        return None
    return dash_videos.find, dash_videos.meta, cfg


def check(ep_dir: Path) -> tuple[bool, str]:
    ep_dir = Path(ep_dir)
    if not ep_dir.is_absolute() and not ep_dir.exists():
        ep_dir = P.EPISODES / ep_dir.name
    ep_dir = ep_dir.resolve()
    here = profiles.of(ep_dir)  # the channel it belongs to: its settings, and its own ReelForge profile
    profiles.use(here)
    lines: list[str] = []
    ok = True

    spec_file = ep_dir / "episode.json"
    if not spec_file.exists():
        return False, f"  FAIL  no episode.json in {ep_dir}"
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    video = ep_dir / "final" / f"{spec['id']}.mp4"
    cap = ep_dir / "final" / "caption.txt"
    qa = ep_dir / "build" / "qa" / "qa.json"
    s = S.load(here.settings)
    reviewed_digest = None

    def item(good: bool, text: str):
        nonlocal ok
        ok = ok and good
        lines.append(f"  {'OK  ' if good else 'FAIL'}  {text}")

    item(video.exists(), f"video file {video.relative_to(ROOT) if video.is_relative_to(ROOT) else video}")
    item(cap.exists(), "final/caption.txt (the Publish tab reads the hashtags from it)")
    if qa.exists() and video.exists():
        q = json.loads(qa.read_text(encoding="utf-8"))
        try:
            fresh = receipts.qa_matches(q, receipts.snapshot(ep_dir, spec, s))
        except (OSError, ValueError) as exc:
            fresh = False
            lines.append(f"  note  review inputs could not be verified: {exc}")
        reviewed_digest = q.get("review_fingerprint") if fresh else None
        item(bool(q.get("pass")) and fresh, "QA passed on this exact file" if q.get("pass") and fresh
             else "QA failed, or the video, cover, captions or inputs changed after QA (rerun --steps qa)")
    else:
        item(False, "QA report (run --steps post)")
    item(bool(reviewed_digest) and review_approved(ep_dir / "build" / "qa" / "review.md", reviewed_digest),
         "your review (build/qa/review.md) says APPROVED for these exact artifacts and inputs")

    title = " ".join(str(spec.get("title", "")).split())
    tags_line = ""
    if cap.exists():
        parts = [p.strip() for p in cap.read_text(encoding="utf-8").split("\n\n") if p.strip()]
        if len(parts) > 1 and all(w.startswith("#") for w in parts[-1].split()):
            tags_line = parts[-1]
    listing = _dashboard_listing()
    if listing and video.exists():
        find, meta, cfg = listing
        # The tab lists each video once: this final/ file, or its copy in completed videos/ (same file name).
        shown = next((p for p in find(cfg) if p.name.lower() == video.name.lower()), None)
        item(shown is not None, "the Publish tab lists it (checked with the dashboard's own code)")
        got, warnings = meta(shown or video, cfg)
        for w in warnings:
            lines.append(f"  note  {w}")
        item(got.get("caption", "").strip() == S.strip_hashtags(title), f"Publish caption: {got.get('caption', '')!r}")
        tags_line = got.get("tags") or tags_line
    elif video.exists():
        item(True, "the Publish tab will list it (episodes/<id>/final/<id>.mp4)")
        lines.append("  note  the dashboard isn't set up yet, so this used the same rules directly")
    tags = S.tag_list(tags_line or spec.get("hashtags", []))
    if not tags and s["captions"]["max_hashtags"] > 0:
        item(False, "hashtags (episode.json 'hashtags')")
    posts = S.post_texts(title, tags, s)
    lines.append("")
    lines.append("  What each platform will get:")
    for p, text in posts.items():
        shown = text.strip().replace("\n\n", "  |  description: ")
        lines.append(f"    {S.PLATFORM_NAMES[p]:<16} {shown}")
    done = ([d for d in here.completed.glob(f"{spec['id']} - *") if (d / video.name).exists()]
            if here.completed.exists() else [])
    lines.append("")
    lines.append(f"  Copy in completed videos: {'yes' if done else 'no (run --steps deliver)'}")
    head = "READY in ReelForge -> Publish" if ok else "NOT READY for ReelForge's Publish tab"
    return ok, f"  {head}: {spec['id']}\n" + "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m studio publish-check episodes/<id>")
        return 2
    ok, report = check(Path(argv[0]))
    print(report)
    return 0 if ok else 1
