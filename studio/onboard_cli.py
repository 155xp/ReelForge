"""The onboarding interview as plain questions and answers, for terminals where the full-screen app won't run
(`python -m studio onboard --plain`)."""

from __future__ import annotations

from . import KIT_NAME, signup
from .questions import QUESTIONS, STEPS, coerce, defaults_for, validate


def _show_default(q, d) -> str:
    if d in (None, "", []):
        return ""
    if q.kind == "yesno":
        return "Y/n" if d else "y/N"
    if q.kind == "choice":
        values = [v for v, _ in q.options]
        return str(values.index(d) + 1) if d in values else str(d)
    if q.kind == "multi":
        values = [v for v, _ in q.options]
        return ",".join(str(values.index(x) + 1) for x in d if x in values)
    if isinstance(d, list):
        return "; ".join(d)
    return str(d).replace("\n", "; ")


def ask(answers: dict | None = None, inp=input, out=print) -> dict:
    a = defaults_for(dict(answers or {}))
    out(f"\n{KIT_NAME}: set up your channel. Press Enter to keep the answer in [brackets].\n")
    for step, label in STEPS:
        out(f"\n== {label} ==")
        if step == "accounts":
            out(f"\nStarting from scratch? {signup.GMAIL.title} first: {signup.GMAIL.url}\n  {signup.GMAIL.why}")
        for q in QUESTIONS:
            if q.step != step or not q.visible(a):
                continue
            if q.key in ("series", "twist", "default_tags", "hud") and q.key not in (answers or {}):
                a.pop(q.key, None)             # follow the format picked a moment ago
                a = defaults_for(a)
            d = a.get(q.key, q.default_for(a))
            out(f"\n{'Your ' + q.prompt + ' handle' if q.kind == 'handle' else q.prompt}" +
                (" (required)" if q.required else ""))
            if q.help:
                out(f"  {q.help}")
            if q.kind == "handle":
                out(f"  No account yet? Sign up at {signup.GUIDES[q.key.removeprefix('handle_')].url} "
                    "(Enter skips: connect it later on ReelForge's Accounts tab)")
            if q.kind in ("choice", "multi"):
                for n, (_, lab) in enumerate(q.options, 1):
                    out(f"  {n}. {lab}")
                if q.kind == "multi":
                    out("  (numbers separated by commas)")
            if q.kind == "long":
                out("  (separate several items with ;)")
            while True:
                shown = _show_default(q, d)
                raw = inp(f"> [{shown}] " if shown else "> ").strip()
                if not raw:
                    raw = d if d not in (None,) else ""
                elif q.kind == "long":
                    raw = "\n".join(x.strip() for x in raw.split(";") if x.strip())
                try:
                    value = coerce(q, raw)
                except ValueError as e:
                    out(f"  {e}")
                    continue
                if q.required and value in (None, "", []):
                    out("  Please answer this one.")
                    continue
                a[q.key] = value
                break
    clean, problems = validate(a)
    for p in problems:
        out(f"  needs fixing: {p}")
    return clean
