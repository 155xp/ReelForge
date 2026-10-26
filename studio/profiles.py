"""Profiles: one for each channel. A profile has its own accounts, log-ins, stats history, notifications, Publish list
and settings, and your AI's notes on that channel.

The first profile is the ReelForge folder's own channel, whose files stay where ReelForge has always kept them
(my-studio/, episodes/, completed videos/, dashboard/config.toml, dashboard/data/). Each channel you add gets a
folder in profiles/, laid out the same way:

  profiles/<name>/profile.toml        its name, and when it was made
  profiles/<name>/my-studio/          its onboarding answers, settings and channel bible
  profiles/<name>/CLAUDE.md           your AI's notes on the channel (and AGENTS.md)
  profiles/<name>/episodes/           its videos in the making; completed videos/ once they're done
  profiles/<name>/dashboard/          its ReelForge settings (config.toml) and data/: its stats, notifications and a
                                      browser profile of its own, so its log-ins are its own

Whatever ReelForge runs works on one profile: the one REELFORGE_PROFILE names (its folder from the ReelForge folder:
"." for the first, "profiles/<name>" for the others), else the first. The window starts its Python side with the
profile it shows and starts a new one when you switch; the hourly stats job reads each profile in turn, each in a
process of its own; the video pipeline goes by the folder the episode is in.

Standard library only: the window's Python side and the launchers read it before anything else.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "profiles"
ENV = "REELFORGE_PROFILE"
MARK = "profile.toml"       # in a profile's folder: what makes it one
LAST = "last-opened.txt"    # in profiles/: the profile the window showed last, which it opens on next time


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class Profile:
    folder: Path   # the ReelForge folder itself for the first profile, profiles/<name> for the others

    @property
    def main(self) -> bool:
        """The first profile: the ReelForge folder's own channel."""
        return _same(self.folder, ROOT)

    @property
    def key(self) -> str:
        """How REELFORGE_PROFILE (and the window) names it: "." or "profiles/<name>"."""
        if self.main:
            return "."
        if _same(self.folder.parent, FOLDER):
            return f"profiles/{self.folder.name}"
        return str(self.folder)

    @property
    def slug(self) -> str:
        """The short name typed after -p: its folder's name ("cool-epic-facts"), or the first one's name as one."""
        return slug_for(self.name) if self.main else self.folder.name

    @property
    def name(self) -> str:
        """The channel's name: from its onboarding settings, else from profile.toml (or, for the first profile, the
        name older versions kept in the dashboard's config.toml)."""
        channel = _toml(self.settings).get("channel")
        name = str(channel.get("name", "")).strip() if isinstance(channel, dict) else ""
        name = name or str(_toml(self.folder / MARK).get("name", "")).strip()
        if not name and self.main:
            name = str(_toml(self.config).get("name", "")).strip()
        return name or ("My channel" if self.main else self.folder.name.replace("-", " ").title())

    @property
    def created(self) -> str:
        return "" if self.main else str(_toml(self.folder / MARK).get("created", ""))

    # its files, laid out like the ReelForge folder's own
    @property
    def my_studio(self) -> Path:
        return self.folder / "my-studio"

    @property
    def answers(self) -> Path:
        return self.my_studio / "answers.json"

    @property
    def settings(self) -> Path:
        return self.my_studio / "studio.toml"

    @property
    def bible(self) -> Path:
        return self.my_studio / "channel-bible.md"

    @property
    def backups(self) -> Path:
        return self.my_studio / "backups"

    @property
    def episodes(self) -> Path:
        return self.folder / "episodes"

    @property
    def completed(self) -> Path:
        return self.folder / "completed videos"

    @property
    def dashboard(self) -> Path:
        """Its ReelForge settings and data (the first profile's sit beside the window's own code, in dashboard/)."""
        return self.folder / "dashboard"

    @property
    def config(self) -> Path:
        return self.dashboard / "config.toml"

    @property
    def data(self) -> Path:
        return self.dashboard / "data"

    @property
    def db(self) -> Path:
        return self.data / "stats.db"

    @property
    def onboarded(self) -> bool:
        return self.settings.is_file()

    def describe(self) -> str:
        """Where it is, for messages: "this folder" or profiles/<name>."""
        return "the ReelForge folder" if self.main else f"profiles{os.sep}{self.folder.name}"


def main() -> Profile:
    return Profile(ROOT)


def extra() -> list[Profile]:
    """The channels added since the first, oldest first."""
    try:
        folders = [d for d in FOLDER.iterdir() if d.is_dir() and (d / MARK).is_file()]
    except OSError:
        return []
    found = [Profile(d) for d in folders]
    return sorted(found, key=lambda p: (p.created, p.name.casefold(), p.folder.name))


def every() -> list[Profile]:
    """Every profile, the first one first."""
    return [main(), *extra()]


def several() -> bool:
    return bool(extra())


def get(key: str | os.PathLike | None) -> Profile | None:
    """The profile a key (".", "profiles/<name>" or a folder's full path) names, if there's one there."""
    key = str(key or "").strip()
    if not key:
        return None
    if key in (".", "./", ".\\"):
        return main()
    path = Path(key)
    if not path.is_absolute():
        path = ROOT / path
    if _same(path, ROOT):
        return main()
    if (path / MARK).is_file():
        return Profile(path)
    return None


def current() -> Profile:
    """The profile this process works on: REELFORGE_PROFILE's, else the first one."""
    return get(os.environ.get(ENV)) or main()


def use(profile: Profile) -> None:
    """Work on this profile from now on, here and in every program started from here."""
    os.environ[ENV] = profile.key


def find(word: str) -> Profile | None:
    """The profile typed after -p: its number in the list (1 is the first), its name or short name (any case), the
    start of either when only one profile starts that way, or its folder."""
    word = (word or "").strip()
    if not word:
        return None
    every_ = every()
    if word.isdigit():
        n = int(word)
        return every_[n - 1] if 1 <= n <= len(every_) else None
    if word in (".", "./", ".\\") or "/" in word or "\\" in word:
        return get(word)
    low = word.casefold()
    for p in every_:
        if low in (p.name.casefold(), p.slug.casefold()):
            return p
    slug = slug_for(word)
    starts = [p for p in every_ if p.name.casefold().startswith(low) or p.slug.startswith(slug)]
    return starts[0] if len(starts) == 1 else None


def of(path: str | os.PathLike) -> Profile:
    """The profile a file or folder belongs to: the one whose folder in profiles/ it's in, else the first."""
    try:
        rel = Path(path).resolve().relative_to(FOLDER.resolve())
    except (OSError, ValueError):
        return main()
    if rel.parts and (FOLDER / rel.parts[0] / MARK).is_file():
        return Profile(FOLDER / rel.parts[0])
    return main()


def last() -> Profile:
    """The profile the window showed last (the one it opens on), else the first."""
    try:
        key = (FOLDER / LAST).read_text(encoding="utf-8").strip()
    except OSError:
        return main()
    return get(key) or main()


def remember(profile: Profile) -> None:
    """The window shows this profile: it opens on it next time. Nothing's written while there's only the first."""
    if not FOLDER.is_dir():
        return
    try:
        tmp = FOLDER / (LAST + ".tmp")
        tmp.write_text(profile.key + "\n", encoding="utf-8")
        tmp.replace(FOLDER / LAST)
    except OSError:
        pass


def slug_for(name: str) -> str:
    """'Cool Epic Facts!' -> 'cool-epic-facts': a folder name that works on every system."""
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40].strip("-")
    return slug or "channel"


def taken(name: str, but: Profile | None = None) -> Profile | None:
    """Another profile already called this (any case), if there is one."""
    low = (name or "").strip().casefold()
    return next((p for p in every() if p.name.casefold() == low and (but is None or p != but)), None)


def create(name: str) -> Profile:
    """A new profile's folder, profiles/<its name>/ (with -2, -3 ... when that's taken), with its profile.toml.
    Onboarding fills it in."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    base = slug_for(name)
    for n in range(1, 1000):
        folder = FOLDER / (base if n == 1 else f"{base}-{n}")
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        stamp = datetime.now().isoformat(timespec="seconds")
        (folder / MARK).write_text(
            "# A ReelForge profile: one channel, with its own accounts, log-ins, stats, notifications and settings.\n"
            "# The rest of this folder is laid out like the ReelForge folder (see studio/profiles.py).\n"
            f"name = {json.dumps(name.strip(), ensure_ascii=False)}\ncreated = \"{stamp}\"\n",
            encoding="utf-8", newline="\n")
        return Profile(folder)
    raise OSError(f"couldn't make a folder for {name!r} in {FOLDER}")
