"""reelforge [what]   (the same as: python -m studio [what], from this folder)

  reelforge                    open ReelForge (the first time: first-time setup)
  reelforge 1 .. 6             open a tab: 1 Overview, 2 Videos, 3 Compare, 4 Publish, 5 Accounts, 6 Updates
  reelforge videos             tabs by name work too: overview, videos, compare, publish, accounts, updates
  reelforge --demo             try ReelForge on made-up stats
  reelforge refresh            read every profile's stats once and exit

  reelforge profiles           your profiles: one for each channel, with its own accounts, stats and settings
  reelforge profiles new       add one (the same interview as your first channel's)
  reelforge -p NAME ...        any command, for one profile: its name, the start of it, or its number in the list
                               (the window opens on the one you had open last; everything else works on the first)

  reelforge setup [--yes]      set up or repair: Blender, ffmpeg, the sounds, the reelforge command, then your channel
  reelforge channel            your channel's questions from first-time setup, to change your answers; it
                               writes CLAUDE.md / AGENTS.md (reelforge onboard, its old name, works too)
      --plain                  the same questions as plain prompts
      --questions              the questions as JSON (for an AI running the interview in chat)
      --answers FILE.json      write everything from saved answers, no questions
      --regenerate             rebuild everything from my-studio/answers.json (e.g. after an update), every profile's
      --new                    for a new profile (with --answers too, for an AI running the interview in chat)
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
import os
import re
import sys
from pathlib import Path

from . import KIT_NAME, profiles
from . import paths as P


def _print_written(paths: list[Path]) -> None:
    print("\nWritten:")
    for p in paths:
        print(f"  {P.rel(p)}")


def next_steps(profile=None) -> str:
    """What to do once onboarding has written a profile's files (the one this process works on, by default)."""
    from . import settings as S
    profile = profile or profiles.current()
    s = S.load(profile.settings)
    who = s["ai"]["assistant"]
    lines = ["", "Your studio is ready. Next:" if profile.main else f"{s['channel']['name']} is ready. Next:"]
    if who in ("claude", "both"):
        lines.append("  1. Open this folder in Claude Code: in the Claude desktop app, open Code and choose this "
                     "folder (or run `claude` in a terminal here). It reads CLAUDE.md by itself." if profile.main else
                     "  1. Open the ReelForge folder in Claude Code, as for every channel: its CLAUDE.md lists this "
                     "one, and this channel's own notes are in its folder.")
    if who in ("codex", "both"):
        lines.append(("  1. " if who == "codex" else "     ") + "Codex: run `codex` in a terminal in "
                     f"{'this' if profile.main else 'the ReelForge'} folder. It reads AGENTS.md by itself.")
    video = "my first video" if profile.main else f"my first {s['channel']['name']} video"
    say, kept = ("here's my channel", "your channel's brief") if profile.main else \
        (f"here's {s['channel']['name']}", f"the brief for {s['channel']['name']}")
    lines.append(f'  2. Say "{say}" and drag a file about it into the chat, or paste a description (your notes, a '
                 f"doc, examples you like). It keeps it as {kept} and plans every video from it.")
    lines.append(f'  3. Say: "make {video}"')
    icon = ("double-click ReelForge.bat" if P.WINDOWS else "open ReelForge from Applications" if P.MAC else
            "open ReelForge from your app menu")
    lines.append(f"  4. When it's done, open ReelForge (type reelforge, or {icon}) and go to Publish (tab 4) to post "
                 "it.")
    return "\n".join(lines)


def apply_background_stats() -> str:
    """Turn the hourly stats job on or off to match the profiles' settings (my-studio/studio.toml): one job reads every
    profile that wants it, so it's on while any of them does."""
    from . import settings as S
    from . import stats_schedule
    try:
        if any(S.load(p.settings)["platforms"].get("background_stats", True) for p in profiles.every()):
            return stats_schedule.enable()
        if stats_schedule.status() == "on":
            return stats_schedule.disable()
        return "Background stats are off (turn them on with: reelforge stats on)."
    except Exception as e:  # the scheduler isn't available: say so, don't fail onboarding
        return f"Background stats couldn't be set up ({e}). Try: reelforge stats on"


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def onboard(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="reelforge channel")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--answers", type=Path)
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--questions", action="store_true")
    ap.add_argument("--new", action="store_true")
    args = ap.parse_args(argv)
    from . import generate, questions

    if args.questions:
        print(json.dumps(questions.describe(), indent=2, ensure_ascii=False))
        return 0
    if args.regenerate and not args.answers:
        return regenerate()
    if args.answers or args.regenerate:
        src = args.answers or P.ANSWERS
        if not src.exists():
            print(f"{src} not found. Run first-time setup first: reelforge channel")
            return 1
        try:
            answers = json.loads(src.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            print(f"{src} isn't valid JSON: {e}")
            return 1
        target = None
        if args.new:  # a new profile: its own folder in profiles/, named after the channel
            a, problems = questions.validate(answers)
            if problems:
                print("some answers need fixing:\n  " + "\n  ".join(problems))
                return 1
            if other := profiles.taken(str(a.get("channel_name") or "")):
                print(f"You already have a profile called {other.name}: give the new channel its own name.")
                return 1
            target = profiles.create(a["channel_name"])
            answers = {**answers, "_created": ""}
        try:
            written = generate.write_all(answers, target)
        except ValueError as e:
            print(e)
            return 1
        _print_written(written)
        if target is not None:
            print(f"\nNew profile: {target.name} ({target.describe()}). Open it with: reelforge -p {target.slug}")
        if not args.regenerate:
            print("\n" + apply_background_stats())
        print(next_steps(target))
        return 0
    if args.plain or not _interactive():
        if not sys.stdin.isatty():
            print("No interactive terminal here. Answer your channel's questions yourself (reelforge channel, or "
                  "channel.bat / ./channel.sh), or write the answers to a JSON file and use: reelforge channel "
                  "--answers FILE.json\n(reelforge channel --questions lists the questions.)")
            return 2
        if args.new:
            print("Use the full-screen interview for a new profile (reelforge profiles new), or write the answers to a "
                  "JSON file: reelforge channel --new --answers FILE.json")
            return 2
        from . import onboard_cli
        prior = json.loads(P.ANSWERS.read_text(encoding="utf-8")) if P.ANSWERS.exists() else None
        answers = onboard_cli.ask(prior)
        written = generate.write_all(answers)
        _print_written(written)
        print("\n" + apply_background_stats())
        print(next_steps())
        return 0
    return first_run("onboard", new=args.new)


def regenerate() -> int:
    """Every profile's files again from its saved answers (after an update, so they get the new version's
    instructions): the first one last, so its notes list the others as they are now."""
    from . import generate

    done = 0
    for p in [*profiles.extra(), profiles.main()]:
        if not p.answers.exists():
            continue
        try:
            answers = json.loads(p.answers.read_text(encoding="utf-8-sig"))
            written = generate.write_all(answers, p)
        except (ValueError, OSError) as e:
            print(f"{p.name}: {e}")
            continue
        done += 1
        if p.main:
            _print_written(written)
    if not done:
        print(f"{P.ANSWERS} not found. Run first-time setup first: reelforge channel")
        return 1
    return 0


def first_run(start: str, new: bool = False) -> int:
    """The first-run screens (the OpenTUI app's: the tools, onboarding, then what to do next), from `start`. When
    their last button asks for it, ReelForge opens next, on the tab (and the profile) it picked. new: onboarding makes
    a new profile."""
    from . import tui, ui

    tui.set_title(f"{KIT_NAME} TEST setup" if P.test_copy() else f"{KIT_NAME} setup")
    code, result = ui.run("setup", {"start": start, "new": new})
    if result and result.get("open") == "dashboard":
        made = profiles.get(result.get("profile"))
        if made is not None:
            profiles.use(made)
        return dashboard([result.get("tab") or "overview"])
    return code


def list_profiles(argv: list[str]) -> int:
    """reelforge profiles [new]: every profile, or the interview that adds one."""
    if argv and argv[0] in ("new", "add"):
        return first_run("onboard", new=True) if _interactive() else onboard(["--new", *argv[1:]])
    if argv:
        print("usage: reelforge profiles [new]")
        return 2
    here = profiles.current() if profiles.get(os.environ.get(profiles.ENV)) else profiles.last()
    print("Your profiles (one for each channel):")
    for i, p in enumerate(profiles.every(), 1):
        mark = "*" if p == here else " "
        print(f"  {mark} {i}. {p.name:<28} {p.describe()}")
    print("\nreelforge -p NAME opens one (the name, the start of it, or its number); reelforge profiles new adds one.")
    return 0


def take_profile(argv: list[str]) -> tuple[list[str], str | None]:
    """-p NAME / --profile NAME / --profile=NAME, wherever it is, out of the command: (the rest, NAME or None)."""
    rest, word, i = [], None, 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--profile") and i + 1 < len(argv):
            word, i = argv[i + 1], i + 2
            continue
        if a.startswith("--profile="):
            word = a.split("=", 1)[1]
        else:
            rest.append(a)
        i += 1
    return rest, word


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
        from dashboard.tabs import tab_for as dash_tab_for
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
        return first_run("tools" if state == "setup" else "onboard")
    if state == "setup":
        print("ReelForge isn't set up yet: run reelforge setup (or setup.bat / ./setup.sh).")
    elif state == "onboard":
        print("Your channel isn't set up yet: run reelforge channel.")
    return dashboard(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)    # keep our lines in order with the tools' output in logs
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    P.keep_runnable()
    argv, word = take_profile(argv)
    if word is not None:
        chosen = profiles.find(word)
        if chosen is None:
            names = ", ".join(f"{i}. {p.name}" for i, p in enumerate(profiles.every(), 1))
            print(f"There's no profile called {word!r}. Your profiles: {names}")
            return 2
        profiles.use(chosen)
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
    if cmd in ("channel", "onboard"):
        return onboard(rest)
    if cmd == "profiles":
        return list_profiles(rest)
    if cmd == "setup":
        yes = "--yes" in rest or "-y" in rest
        if not yes and _interactive():
            return first_run("tools")
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
