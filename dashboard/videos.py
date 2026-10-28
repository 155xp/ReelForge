"""Finding finished cuts and the text that goes with them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import config

VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
X_LIMIT = 280

# Post format. The caption is one short line, e.g. "What would happen if gravity doubled every second".
#   X: the caption.  YouTube: the caption is the title, the hashtags are the description.
#   TikTok: caption + hashtags, FIRST_TAG first.  Instagram: caption + hashtags.
# The limits come from the studio's settings (my-studio/studio.toml, written by onboarding) so ReelForge and the video
# pipeline always agree; without them: 5 hashtags, #fyp first on TikTok, none on X.


def _rules() -> tuple[int, str, bool]:
    try:
        import sys

        root = str(config.APP_DIR.parent)
        if root not in sys.path:
            sys.path.append(root)
        from studio import settings as studio_settings

        c = studio_settings.load()["captions"]
        return int(c["max_hashtags"]), str(c["tiktok_first_tag"]), bool(c["hashtags_on_x"])
    except Exception:
        return 5, "fyp", False


MAX_TAGS, FIRST_TAG, X_TAGS = _rules()
_HASHTAG = re.compile(r"(?<![\w&])#\w+")


def tag_list(tags: str) -> list[str]:
    """'#a b #A #c' -> ['#a', '#b', '#c']: hashtags in order, # added, repeats dropped."""
    out, seen = [], set()
    for word in tags.replace(",", " ").split():
        tag = "#" + word.lstrip("#")
        if len(tag) > 1 and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out


def clean_tags(tags: str) -> str:
    """At most MAX_TAGS hashtags, as typed."""
    return " ".join(tag_list(tags)[:MAX_TAGS])


def tiktok_tags(tags: str) -> str:
    """FIRST_TAG (normally #fyp) first, then the others, MAX_TAGS in all."""
    if not FIRST_TAG:
        return clean_tags(tags)
    first = "#" + FIRST_TAG
    rest = [t for t in tag_list(tags) if t.lower() != first.lower()]
    return " ".join([first, *rest][:MAX_TAGS])


def _hashtag_token(word: str) -> bool:
    """A word that is only hashtags, with an optional .,!? after the last ('#fyp', '#fyp#whatif.')."""
    return re.fullmatch(r"(#\w+)+[.,!?]*", word) is not None


def strip_hashtags(text: str) -> str:
    """The caption without its hashtags, on one line. The hashtags tacked on at the end go ("Gravity flipped?
    #fyp #whatif"); one inside the sentence keeps its word ("What if #gravity doubled" -> "What if gravity
    doubled"). A single hashtag at the very end counts as tacked on only after a ?, ! or full stop. Hashtags
    glued together ("#fyp#whatif") are tags, not a word, so they go wherever they sit."""
    words = text.split()
    tail = 0
    while tail < len(words) and _hashtag_token(words[len(words) - 1 - tail]):
        tail += 1
    before = words[len(words) - 1 - tail] if tail < len(words) else ""
    glued_tail = any(w.count("#") > 1 for w in words[len(words) - tail:])
    if tail and (tail >= 2 or tail == len(words) or before[-1:] in "?!." or glued_tail):
        words = words[:len(words) - tail]
    words = [w for w in words if not (w.count("#") > 1 and _hashtag_token(w))]
    return " ".join(_HASHTAG.sub(lambda m: m.group(0)[1:], " ".join(words)).split())


def caption_tags(text: str) -> list[str]:
    """The hashtags written in a caption, including ones glued together ("#fyp#whatif")."""
    return [f"#{tag}" for word in text.split() if word.startswith("#") for tag in re.findall(r"#(\w+)", word)]


def post_text(platform: str, caption: str, tags: str) -> str:
    """What goes in a platform's text box (for YouTube, the description; the caption is its title).

    Hashtags typed into the caption are moved to the hashtag list, so the limit of 5 always holds.
    """
    body = strip_hashtags(caption)
    all_tags = " ".join([*caption_tags(caption), tags])
    if platform == "x":
        return f"{body} {clean_tags(all_tags)}".strip() if X_TAGS else body
    if platform == "youtube":
        return clean_tags(all_tags)
    line = tiktok_tags(all_tags) if platform == "tiktok" else clean_tags(all_tags)
    return f"{body} {line}".strip()


def find(cfg: dict) -> list[Path]:
    """Every finished cut, newest first: the videos folder, each pipeline episode's final/ folder and the
    pipeline's completed-videos folder. A video found in two places (final/ and completed) is listed once."""
    found: list[Path] = []
    folder = config.videos_dir(cfg)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        found += [f for f in folder.iterdir() if f.suffix.lower() in VIDEO_EXTS]
    except OSError:
        pass  # e.g. a drive that isn't plugged in: list what the other folders have
    for root, pattern in ((config.episodes_dir(cfg), "*/final/*"), (config.completed_dir(cfg), "*/*")):
        if root.is_dir():
            found += [f for f in root.glob(pattern) if f.suffix.lower() in VIDEO_EXTS]

    def mtime(f: Path) -> float:
        try:
            return f.stat().st_mtime
        except OSError:
            return -1.0

    newest: dict[str, Path] = {}
    # newest first; a copy with the same time (completed videos/ keeps it) loses to the pipeline's final/ file
    for f in sorted({f.resolve() for f in found if f.is_file()},
                    key=lambda f: (mtime(f), from_pipeline(f)), reverse=True):
        if mtime(f) >= 0:
            newest.setdefault(f.name.lower(), f)
    return list(newest.values())


def from_pipeline(path: Path) -> bool:
    return path.parent.name == "final" and (path.parent.parent / "episode.json").exists()


def episode_dir(path: Path, cfg: dict) -> Path | None:
    """The pipeline folder a video was rendered in (episodes/<id>/), wherever the video file now sits."""
    if from_pipeline(path):
        return path.parent.parent
    folder = config.episodes_dir(cfg) / path.stem
    return folder if (folder / "episode.json").exists() else None


def split_caption(text: str) -> tuple[str, str]:
    """caption.txt is the caption, a blank line, then a line of hashtags."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paragraphs) > 1 and all(word.startswith("#") for word in paragraphs[-1].split()):
        return "\n\n".join(paragraphs[:-1]), paragraphs[-1]
    return text.strip(), ""


def meta(path: Path, cfg: dict) -> tuple[dict[str, str], list[str]]:
    """(caption, tags) for a video, plus warnings about files that couldn't be read.

    Caption: <name>.json "caption" (or "title") next to the video, else its pipeline episode's episode.json
    "title" (the hook line), else the file name. Hashtags: <name>.json "tags", else the hashtag line of the
    episode's final/caption.txt, else episode.json "hashtags", else default_tags. 5 are kept.
    """
    found: dict[str, str] = {}
    warnings: list[str] = []

    def read_json(p: Path) -> dict:
        try:
            data = json.loads(p.read_text("utf-8-sig"))
        except (ValueError, OSError) as e:
            warnings.append(f"Couldn't read {p.name}: {e}")
            return {}
        return data if isinstance(data, dict) else {}

    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        side = read_json(sidecar)
        for key in ("caption", "title", "tags"):
            if isinstance(side.get(key), str) and side[key].strip():
                found.setdefault("caption" if key == "title" else key, side[key].strip())

    folder = episode_dir(path, cfg)
    if folder:
        caption_file = folder / "final" / "caption.txt"
        if caption_file.exists():
            try:
                _, tags = split_caption(caption_file.read_text("utf-8-sig"))
            except OSError as e:
                warnings.append(f"Couldn't read {caption_file.name}: {e}")
                tags = ""
            if tags:
                found.setdefault("tags", tags)
        spec = read_json(folder / "episode.json")
        if isinstance(spec.get("title"), str) and spec["title"].strip():
            found.setdefault("caption", spec["title"].strip())
        hashtags = spec.get("hashtags")
        if isinstance(hashtags, str):
            hashtags = hashtags.split()
        if isinstance(hashtags, list) and hashtags:
            found.setdefault("tags", " ".join("#" + str(t).lstrip("#") for t in hashtags))
    default_tags = cfg.get("default_tags", "")

    raw = found.get("caption") or path.stem.replace("_", " ").replace("-", " ").strip().capitalize()
    return {
        "caption": strip_hashtags(raw),
        "tags": clean_tags(" ".join([*caption_tags(raw), found.get("tags") or default_tags])),
    }, warnings
