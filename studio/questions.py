"""The onboarding interview, as data. The terminal wizard, the plain prompts and the AI-led interview
(`python -m studio onboard --questions`, then `--answers file.json`) all use these same questions."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import signup
from .formats import FORMATS, STYLES, TONES
from .settings import LOUDNESS, PLATFORM_NAMES, PLATFORMS, RECOMMENDED


@dataclass
class Q:
    key: str
    step: str
    prompt: str
    kind: str = "text"            # text | long | choice | multi | yesno | number | handle (an @handle, or nothing)
    help: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)   # (value, label)
    default: Any = None           # a value, or a function(answers) -> value
    required: bool = False
    show: Callable[[dict], bool] | None = None
    placeholder: str = ""
    minimum: int | None = None
    maximum: int | None = None

    def visible(self, a: dict) -> bool:
        return self.show is None or bool(self.show(a))

    def default_for(self, a: dict):
        return self.default(a) if callable(self.default) else self.default

    def placeholder_for(self, a: dict) -> str:
        return self.placeholder(a) if callable(self.placeholder) else self.placeholder


STEPS = [
    ("you", "You"),
    ("channel", "Your channel"),
    ("format", "Your format"),
    ("platforms", "Platforms"),
    ("accounts", "Your accounts"),
    ("look", "Look and sound"),
    ("posting", "Captions and posting"),
]


def _fmt(a: dict) -> dict:
    return FORMATS.get(a.get("format") or "doubling", FORMATS["doubling"])


def _has(platform: str) -> Callable[[dict], bool]:
    return lambda a: platform in (a.get("platforms") or PLATFORMS)


def _local_timezone() -> str:
    try:
        tz = _dt.datetime.now().astimezone().tzinfo
        name = getattr(tz, "key", None) or _dt.datetime.now().astimezone().tzname() or ""
        return str(name)
    except Exception:  # pragma: no cover
        return ""


def _default_tags(a: dict) -> str:
    first = (a.get("tiktok_first_tag") or "fyp").lstrip("#")
    tags = [first] + [t for t in _fmt(a)["tags"] if t != first]
    return " ".join("#" + t for t in tags[:5])


QUESTIONS: list[Q] = [
    # ---- you
    Q("creator", "you", "What should your AI call you?", help="Your first name or nickname. Optional.",
      placeholder="Sam"),
    Q("assistant", "you", "Which AI will make your videos?", "choice", default="claude",
      help="It needs to run commands on this computer: Claude Code (the Claude desktop app's Code tab, or the "
           "claude command) or OpenAI's Codex CLI.",
      options=[("claude", "Claude Code (recommended)"), ("codex", "Codex"), ("both", "Both")]),

    # ---- channel
    Q("channel_name", "channel", "What's your channel called?", required=True, placeholder="Night Physics",
      help="Shown in ReelForge and in your AI's notes. It is not stamped on the videos."),
    Q("about", "channel", "What do you want your content to be about?", "long", required=True,
      placeholder="Mind-bending what-if videos: everyday things pushed to impossible extremes, with real science.",
      help="One or two sentences. Your AI uses this to pick every subject."),
    Q("audience", "channel", "Who is it for?", placeholder="Teens and adults who like science, space and games"),
    Q("tone", "channel", "How should viewers feel?", "multi", default=["awe", "suspense"],
      options=[(t, t.capitalize()) for t in TONES], help="Pick one or more."),

    # ---- format
    Q("format", "format", "Which format do you want to start with?", "choice", default="doubling",
      options=[(k, f["label"] + ("   · ready-made 3D scenes" if f["built_in"] else "")) for k, f in FORMATS.items()],
      help="Proven formats first: your AI copies what is already pulling views, then does it better. "
           "'Ready-made 3D scenes' means the kit already has working scenes for it."),
    Q("custom_format", "format", "Describe your format", "long", required=True,
      show=lambda a: a.get("format") == "custom",
      placeholder="Each video: a question at the top, a 3D scene that escalates, a counter, a twist at the end...",
      help="The hook, how a video escalates, and how it ends."),
    Q("series", "format", "Name your first series", default=lambda a: _fmt(a)["series"], required=True,
      placeholder="Doubling", help="Videos in a series share a title pattern and an 'Ep. N' label."),
    Q("twist", "format", "Your signature twist (what makes your version different)", "long",
      default=lambda a: _fmt(a)["twist"],
      help="Copycats arrive fast. A recognisable ending or effect makes your videos yours."),
    Q("references", "format", "Creators or videos you want to beat", "long",
      placeholder="@someone on TikTok\nhttps://www.youtube.com/shorts/...",
      help="Optional. One per line. Your AI studies these first."),
    Q("subjects", "format", "Ideas for your first videos", "long",
      placeholder=lambda a: "\n".join(_fmt(a)["subjects"][:4]),
      help="Optional. One per line. Your AI adds its own and never repeats a subject."),
    Q("avoid", "format", "Anything to avoid?", placeholder="Gore, real brands, politics",
      help="Optional. Topics, words or looks your videos should never have."),

    # ---- platforms
    Q("platforms", "platforms", "Where will you post?", "multi", default=list(RECOMMENDED), required=True,
      options=[(p, PLATFORM_NAMES[p] + ("   · recommended" if p in RECOMMENDED else "")) for p in PLATFORMS],
      help="Recommended: TikTok, YouTube Shorts and Instagram Reels, the three big short-video apps. You can add or "
           "remove one later on ReelForge's Accounts tab."),
    Q("background_stats", "platforms", "Keep reading your stats every hour, even when ReelForge is closed?", "yesno",
      default=True, help="Adds a small background job that runs while your computer is on, so your charts never "
                         "miss an hour. Turn it off any time with: reelforge stats off"),

    # ---- accounts: a handle each, or a sign-up guide (the Gmail one first, for a channel starting from scratch)
    *[Q(f"handle_{p}", "accounts", PLATFORM_NAMES[p], "handle", show=_has(p), placeholder="@yourname",
        help="It needs one log-in in ReelForge too, so ReelForge can read your stats: it asks when you open it."
        if p in ("instagram", "x") else "") for p in PLATFORMS],

    # ---- look and sound
    Q("style", "look", "What should your videos look like?", "choice", default="cinematic",
      options=list(STYLES.items())),
    Q("style_notes", "look", "Describe the look", "long", show=lambda a: a.get("style") == "custom",
      required=True, placeholder="Pastel colours, toy-like 3D, soft shadows"),
    Q("hud", "look", "Show a big on-screen counter, like a game HUD?", "yesno",
      default=lambda a: _fmt(a)["hud"], help="It ticks up (or down) as the video escalates. No box behind it."),
    Q("cta", "look", "The call-to-action at the end of every video", default="FOLLOW FOR MORE"),
    Q("loudness", "look", "How loud should your videos be?", "choice", default="quiet",
      options=[(k, v[1]) for k, v in LOUDNESS.items()]),
    Q("length", "look", "How long should each video be?", "choice", default="61-75",
      options=[("61-75", "61-75 s (recommended: TikTok only pays Creator Rewards on videos over a minute)"),
               ("45-60", "45-60 s"), ("30-45", "30-45 s"), ("custom", "Something else")]),
    Q("length_custom", "look", "Length in seconds (min-max)", show=lambda a: a.get("length") == "custom",
      required=True, placeholder="20-30"),

    # ---- captions and posting
    Q("max_hashtags", "posting", "Most hashtags per post", "number", default=5, minimum=0, maximum=30),
    Q("tiktok_first_tag", "posting", "Hashtag that always goes first on TikTok", default="fyp", show=_has("tiktok"),
      help="Leave empty for none."),
    Q("hashtags_on_x", "posting", "Use hashtags on X?", "yesno", default=False, show=_has("x")),
    Q("default_tags", "posting", "Your usual hashtags", default=_default_tags,
      help="Each video swaps in its own topic tags; these fill the rest."),
    Q("cadence", "posting", "How often do you want to post?", "choice", default="2/day",
      help="Only when I ask: no regular videos, just the ones you ask for.",
      options=[("2/day", "2 videos a day"), ("1/day", "1 video a day"), ("3/week", "3 a week"),
               ("1/week", "1 a week"), ("ask", "Only when I ask")]),
    Q("post_times", "posting", "When do you usually post?", default="8-11 am and 5-8 pm"),
    Q("timezone", "posting", "Your time zone", default=lambda a: _local_timezone()),
]
# Answers older versions saved that nothing reads now: saving the answers drops them. ("quality" was how hard your AI
# should work: that's your AI app's to decide, as the Settings tab's FAQ says.)
RETIRED = ("ultracode", "quality")

BY_KEY = {q.key: q for q in QUESTIONS}


def defaults_for(answers: dict) -> dict:
    """Fill every visible question that has no answer with its default."""
    out = dict(answers)
    for q in QUESTIONS:
        if q.key not in out and q.visible(out):
            d = q.default_for(out)
            if d is not None:
                out[q.key] = d
    return out


def coerce(q: Q, value):
    """A raw answer (string from a prompt, or JSON) -> the right type. Raises ValueError with a readable reason."""
    if q.kind == "yesno":
        if isinstance(value, bool):
            return value
        v = str(value).strip().lower()
        if v in ("y", "yes", "true", "1", "on"):
            return True
        if v in ("n", "no", "false", "0", "off", ""):
            return False
        raise ValueError("answer yes or no")
    if q.kind == "number":
        try:
            n = int(str(value).strip())
        except ValueError:
            raise ValueError("type a whole number") from None
        if q.minimum is not None and n < q.minimum or q.maximum is not None and n > q.maximum:
            raise ValueError(f"pick a number from {q.minimum} to {q.maximum}")
        return n
    if q.kind == "choice":
        values = [v for v, _ in q.options]
        v = str(value).strip()
        if v in values:
            return v
        if v.isdigit() and 1 <= int(v) <= len(values):
            return values[int(v) - 1]
        raise ValueError("pick one of: " + ", ".join(values))
    if q.kind == "multi":
        values = [v for v, _ in q.options]
        items = value if isinstance(value, (list, tuple)) else str(value).replace(",", " ").split()
        out = []
        for item in items:
            item = str(item).strip()
            if item.isdigit() and 1 <= int(item) <= len(values):
                item = values[int(item) - 1]
            if item not in values:
                raise ValueError(f"{item!r} isn't one of: " + ", ".join(values))
            if item not in out:
                out.append(item)
        return out
    if q.kind == "handle":
        return signup.handle_from("" if value is None else str(value))  # "@name", from a link too
    return str(value).strip() if value is not None else ""


def validate(answers: dict) -> tuple[dict, list[str]]:
    """(clean answers with defaults filled, problems). Unknown keys are kept but ignored."""
    a = defaults_for(answers)
    problems = []
    for q in QUESTIONS:
        if not q.visible(a):
            continue
        if q.key in a:
            try:
                a[q.key] = coerce(q, a[q.key])
            except ValueError as e:
                problems.append(f"{q.key}: {e}")
                continue
        empty = a.get(q.key) in (None, "", [])
        if q.required and empty:
            problems.append(f"{q.key}: {q.prompt} (required)")
    if a.get("length") == "custom":
        try:
            lo, hi = parse_length(a.get("length_custom", ""))
            if not 5 <= lo <= hi <= 600:
                raise ValueError
        except ValueError:
            problems.append("length_custom: write it as min-max seconds, e.g. 20-30")
    return a, problems


def parse_length(text: str) -> tuple[float, float]:
    """'61-75', '20 to 30', '45s-60s', '20-30 seconds' or '20–30' -> (min, max) in seconds."""
    raw = str(text).strip().lower().replace("–", "-").replace("—", "-")
    raw = re.sub(r"\bseconds?\b", " ", raw)
    raw = re.sub(r"(\d)\s*s\b", r"\1", raw)  # 20s -> 20, without eating the s in some other word
    raw = raw.replace("to", "-")
    parts = [p for p in re.split(r"\s*-\s*", raw) if p.strip()]
    if not parts:
        raise ValueError("write it as min-max seconds, e.g. 20-30")
    try:
        lo, hi = float(parts[0]), float(parts[-1])
    except ValueError:
        raise ValueError("write it as min-max seconds, e.g. 20-30") from None
    return min(lo, hi), max(lo, hi)


def describe() -> list[dict]:
    """The interview as plain data (for an AI running the interview in chat). A handle question carries the
    platform's sign-up page and steps (signup) for someone without an account yet, and the first one also the Gmail
    a channel starting from scratch can make first (gmail), with what to do for a second channel."""
    out = []
    sample = defaults_for({})
    for q in QUESTIONS:
        d = q.default_for(sample)
        item = {"key": q.key, "step": dict(STEPS)[q.step], "question": q.prompt, "type": q.kind}
        if q.kind == "handle":
            item["question"] = f"Your {q.prompt} handle"
        if q.help:
            item["help"] = q.help
        if q.kind == "handle":
            guide = signup.GUIDES[q.key.removeprefix("handle_")]
            item["signup"] = {"page": guide.url, "steps": guide.steps_for()}
            if not any(i.get("gmail") for i in out):
                item["gmail"] = {"offer": "No accounts yet? Offer to start with a new Gmail for the channel. "
                                          + signup.GMAIL.why, "page": signup.GMAIL.url,
                                 "steps": signup.GMAIL.steps_for(),
                                 "another_channel": "Making accounts for a second channel? They're probably logged in "
                                                    "to the first one in their browser, and most sign-up pages skip "
                                                    "to that account: have them open these pages in a private window "
                                                    "(Ctrl+Shift+N in Chrome and Edge, Ctrl+Shift+P in Firefox; Cmd "
                                                    "instead of Ctrl on a Mac) and keep it open while they make them "
                                                    "all, so they sign up fresh and the first channel stays logged "
                                                    "in."}
        if q.options:
            item["options"] = {v: label for v, label in q.options}
        if d not in (None, "", []):
            item["default"] = d
        if q.required:
            item["required"] = True
        if q.show is not None:
            item["only_if"] = {
                "custom_format": "format is custom", "style_notes": "style is custom",
                "length_custom": "length is custom",
                "tiktok_first_tag": "tiktok is in platforms", "hashtags_on_x": "x is in platforms",
            }.get(q.key, "that platform is in platforms" if q.key.startswith("handle_") else "")
        out.append(item)
    return out
