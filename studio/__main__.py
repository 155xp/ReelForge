"""reelforge [what]   (the same as: python -m studio [what], from this folder)

  reelforge                    open ReelForge (the first time: setup, then onboarding)
  reelforge 1 .. 6             open a tab: 1 Overview, 2 Videos, 3 Compare, 4 Publish, 5 Accounts, 6 Updates
  reelforge videos             tabs by name work too: overview, videos, compare, publish, accounts, updates
  reelforge --demo             try ReelForge on made-up stats
  reelforge refresh            read your stats once and exit

  reelforge setup [--yes]      set up or repair: Blender, ffmpeg, the sounds, the reelforge command, then onboarding
  reelforge onboard            the interview that sets up your channel and writes CLAUDE.md / AGENTS.md
      --plain                  the same questions as plain prompts
      --questions              the questions as JSON (for an AI running the interview in chat)
      --answers FILE.json      write everything from saved answers, no questions
      --regenerate             rebuild everything from my-studio/answers.json (e.g. after an update)
  reelforge doctor [--render-test]    check everything the pipeline needs
  reelforge stats [on|off]     the hourly job that reads your stats while ReelForge is closed
  reelforge command [on|off]   the reelforge command itself (on your PATH)
  reelforge sounds             download the Mixkit sound effects
  reelforge new-episode SLUG [--from EXAMPLE]   start episodes/epNN_<slug>/ from an example
  reelforge publish-check episodes/<id>         is this video ready in the Publish tab (tab 4)?
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import KIT_NAME
from . import paths as P


def _print_written(paths: list[Path]) -> None:
    print("\nWritten:")
    for p in paths:
        print(f"  {P.rel(p)}")


def next_steps() -> str:
    from . import settings as S
    s = S.load()
    who = s["ai"]["assistant"]
    lines = ["", "Your studio is ready. Next:"]
    if who in ("claude", "both"):
        lines.append("  1. Open this folder in Claude Code: in the Claude desktop app, open Code and choose this "
                     "folder (or run `claude` in a terminal here). It reads CLAUDE.md by itself.")
    if who in ("codex", "both"):
        lines.append(("  1. " if who == "codex" else "     ") + "Codex: run `codex` in a terminal in this folder. "
                     "It reads AGENTS.md by itself.")
    first = "ultracode: make my first video" if s["ai"]["ultracode"] and who != "codex" else "make my first video"
    lines.append(f'  2. Say: "{first}"')
    lines.append("  3. When it's done, open ReelForge (type reelforge, or double-click "
                 + ("ReelForge.bat" if P.WINDOWS else "reelforge.sh") + ") and go to Publish (tab 4) to post it.")
    return "\n".join(lines)


def apply_background_stats() -> str:
    """Turn the hourly stats job on or off to match my-studio/studio.toml."""
    from . import settings as S
    from . import stats_schedule
    try:
        if S.load()["platforms"].get("background_stats", True):
            return stats_schedule.enable()
        if stats_schedule.status() == "on":
            return stats_schedule.disable()
        return "Background stats are off (turn them on with: reelforge stats on)."
    except Exception as e:  # the scheduler isn't available: say so, don't fail onboarding
        return f"Background stats couldn't be set up ({e}). Try: reelforge stats on"


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def onboard(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="reelforge onboard")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--answers", type=Path)
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--questions", action="store_true")
    args = ap.parse_args(argv)
    from . import generate, questions

    if args.questions:
        print(json.dumps(questions.describe(), indent=2, ensure_ascii=False))
        return 0
    if args.answers or args.regenerate:
        src = args.answers or P.ANSWERS
        if not src.exists():
            print(f"{src} not found. Run onboarding first.")
            return 1
        try:
            answers = json.loads(src.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            print(f"{src} isn't valid JSON: {e}")
            return 1
        try:
            written = generate.write_all(answers)
        except ValueError as e:
            print(e)
            return 1
        _print_written(written)
        if not args.regenerate:
            print("\n" + apply_background_stats())
        print(next_steps())
        return 0
    if args.plain or not _interactive():
        if not sys.stdin.isatty():
            print("No interactive terminal here. Run onboarding yourself (reelforge onboard, or onboard.bat / "
                  "./onboard.sh), or write the answers to a JSON file and use: reelforge onboard --answers FILE.json\n"
                  "(reelforge onboard --questions lists the questions.)")
            return 2
        from . import onboard_cli
        prior = json.loads(P.ANSWERS.read_text(encoding="utf-8")) if P.ANSWERS.exists() else None
        answers = onboard_cli.ask(prior)
        written = generate.write_all(answers)
        _print_written(written)
        print("\n" + apply_background_stats())
        print(next_steps())
        return 0
    try:
        from . import firstrun
    except ImportError as e:
        print(f"The full-screen interview needs the Textual package ({e}). Using plain questions instead.")
        return onboard(["--plain"])
    return after_first_run(firstrun.run("onboard"))


def after_first_run(result) -> int:
    """What the first-run screens asked for when they closed: open ReelForge on a tab, or nothing."""
    if result and result[0] == "dashboard":
        return dashboard([result[1]])
    return 0


def new_episode(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="reelforge new-episode",
                                 description="Start episodes/epNN_<slug>/ from an example or an earlier episode.")
    ap.add_argument("slug", help="a short name, e.g. snowball_doubling")
    ap.add_argument("--from", dest="source", default="",
                    help="an example in examples/ or an episode id to copy (default: the example for your format)")
    args = ap.parse_args(argv)
    from . import settings as S
    s = S.load()
    slug = re.sub(r"[^a-z0-9_]+", "_", args.slug.lower()).strip("_")
    if not slug:
        print("give the episode a short name, e.g. snowball_doubling")
        return 2
    P.EPISODES.mkdir(exist_ok=True)
    nums = [int(m.group(1)) for d in P.EPISODES.iterdir() if (m := re.match(r"ep(\d+)_", d.name))]
    ep_id = f"ep{(max(nums) + 1) if nums else 1:02d}_{slug}"
    starters = {"doubling": "demo_doubling_duck", "disaster_pov": "demo_disaster_pov",
                "everyone": "demo_everyone_jumps", "reality_bug": "demo_disaster_pov"}
    source = args.source or starters.get(s["format"]["template"], "")
    if not args.source and not (P.EXAMPLES / source / "episode.json").exists():
        source = next((d.name for d in sorted(P.EXAMPLES.iterdir()) if (d / "episode.json").exists()), "")
    src = next((p / "episode.json" for p in (P.EXAMPLES / source, P.EPISODES / source)
                if source and (p / "episode.json").exists()), None)
    if src is None:
        print(f"no example or episode called {source!r} (examples: "
              f"{', '.join(d.name for d in P.EXAMPLES.iterdir() if d.is_dir())})")
        return 1
    spec = json.loads(src.read_text(encoding="utf-8"))
    spec["id"] = ep_id
    spec["title"] = "WRITE THE HOOK LINE HERE (one question, at most 80 characters)"
    spec["series"] = s["format"]["series"]
    spec.pop("episode_label", None)
    spec.pop("demo", None)                 # a demo carries a DEMO watermark and can't ship; your episode can
    spec.get("hud", {}).pop("brand", None)
    if "cta" in spec or s["video"]["cta"]:
        cta = spec.get("cta", {"start": spec["duration"] - 2.4, "end": spec["duration"] - 0.5})
        cta["text"] = s["video"]["cta"]
        cta.setdefault("sub", "")
        spec["cta"] = cta
    tags = S.tag_list(s["captions"]["default_tags"])[: s["captions"]["max_hashtags"]]
    if tags:
        spec["hashtags"] = tags
    dest = P.EPISODES / ep_id
    dest.mkdir()
    from . import jsonfmt
    jsonfmt.write(dest / "episode.json", spec)
    facts = (P.TEMPLATES / "facts.md").read_text(encoding="utf-8").replace("{id}", ep_id)
    (dest / "facts.md").write_text(facts, encoding="utf-8")
    print(f"Started {P.rel(dest)} from {P.rel(src.parent)}.")
    print("Next: write the title, lines, HUD, sound cues and facts.md, then build and look at the stills:")
    print(f"  {P.venv_python()} {Path('pipeline') / 'make_episode.py'} {Path('episodes') / ep_id} "
          f"--steps build,stills")
    return 0


# ---------------------------------------------------------------- the ReelForge window

def ready_state() -> str:
    """'setup' while a tool is missing, 'onboard' until the channel is set up, '' when ReelForge is ready."""
    from . import settings as S
    from . import sounds, tools
    if not tools.find_blender() or not tools.find_ffmpeg() or sounds.missing():
        return "setup"
    return "" if S.onboarded() else "onboard"


def tab_for(word: str) -> str | None:
    """'4' or 'publish' -> the dashboard's tab id (None if it isn't a tab)."""
    try:
        from dashboard.__main__ import tab_for as dash_tab_for
    except ImportError:
        return None
    return dash_tab_for(word)


def dashboard(argv: list[str]) -> int:
    """Run the ReelForge window in this process; returns its exit code (75 asks the launcher to start it again)."""
    try:
        from dashboard.__main__ import main as dash_main
    except ImportError as e:
        print(f"ReelForge's window can't start: {e}. Run setup again (setup.bat or ./setup.sh).")
        return 3
    try:
        code = dash_main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code or 0


def open_app(argv: list[str]) -> int:
    """`reelforge` with no command: the first-run screens until everything's set up, then the window."""
    state = ready_state()
    if state and _interactive():
        from . import firstrun
        return after_first_run(firstrun.run("tools" if state == "setup" else "onboard"))
    if state == "setup":
        print("ReelForge isn't set up yet: run reelforge setup (or setup.bat / ./setup.sh).")
    elif state == "onboard":
        print("Your channel isn't set up yet: run reelforge onboard.")
    return dashboard(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)    # keep our lines in order with the tools' output in logs
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if not argv:
        return open_app([])
    cmd, rest = argv[0], argv[1:]
    if cmd in ("open", "app", "dashboard"):
        return dashboard(rest)
    if cmd in ("--demo", "refresh") or tab_for(cmd):
        return dashboard(argv)
    if cmd == "onboard":
        return onboard(rest)
    if cmd == "setup":
        yes = "--yes" in rest or "-y" in rest
        if not yes and _interactive():
            from . import firstrun
            return after_first_run(firstrun.run("tools"))
        from . import setup_flow
        return setup_flow.run(yes=yes, onboard="--no-onboard" not in rest)
    if cmd == "doctor":
        from . import doctor
        return doctor.run(render_test="--render-test" in rest)
    if cmd == "stats":
        from . import stats_schedule
        return stats_schedule.main(rest)
    if cmd == "command":
        from . import command
        return command.main(rest)
    if cmd == "sounds":
        from . import sounds
        failed = sounds.fetch_mixkit()
        if not failed:
            sounds.build_cache()
        return 1 if failed else 0
    if cmd == "new-episode":
        return new_episode(rest)
    if cmd == "publish-check":
        from . import publish_check
        return publish_check.main(rest)
    if cmd == "tools":
        from . import tools
        print("blender:", tools.find_blender())
        print("ffmpeg:", tools.find_ffmpeg())
        print("fonts:", *[str(f) for f in tools.find_fonts()], sep="\n  ")
        return 0
    print(f"{KIT_NAME}: there's no command or tab called {cmd!r}.\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
