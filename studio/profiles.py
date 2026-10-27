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

Deleting a channel you've added (delete) takes its folder out of profiles/ whole, into
backups/deleted-profile-<name>-<date>/ in the ReelForge folder: nothing is deleted, and restore puts it back. A
profile a ReelForge window is showing (each window holds a lock in its profile's dashboard/data/windows/ while it's
open) or reading the stats of is left alone, and so is the first, which is the ReelForge folder itself.

Standard library only: the window's Python side and the launchers read it before anything else.
"""

from __future__ import annotations

import errno
import json
import os
import re
import time
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
DELETED = "deleted-profile"  # in backups/: deleted-profile-<its folder>-<date>/, a deleted profile's folder whole
WINDOWS = "windows"         # in a profile's dashboard/data/: a lock for each ReelForge window showing it
READ_LOCK = "stats.refresh.lock"  # ... and the one a ReelForge holds while it reads its stats (dashboard/sync.py)
_STAMP = re.compile(r"-(\d{4}-\d{2}-\d{2}-\d{6})(?: \d+)?$")  # the date at the end of a deleted profile's backup


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
    def channel_name(self) -> str:
        """Its name, or "" while it's a first profile not set up yet (its name is only a stand-in then)."""
        return self.name if self.onboarded or not self.main else ""

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


def others(*besides: Profile | None) -> list[str]:
    """The channel names of every profile except these ("" for a first profile not set up yet)."""
    return [p.channel_name for p in every() if p not in besides]


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
    First-time setup fills it in."""
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


# ---------------------------------------------------------------- deleting a profile, and bringing it back

_BUSY = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}


def backups() -> Path:
    """Where deleted profiles are kept (and factory reset's backups): backups/ in the ReelForge folder."""
    return ROOT / "backups"


def held(lock: Path) -> bool:
    """Whether a ReelForge has this lock file locked right now: a quick try, let go of at once (False when it isn't
    there, or the drive can't lock files)."""
    try:
        fd = os.open(lock, os.O_RDWR)
    except OSError:
        return False
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError as e:
        return e.errno in _BUSY
    finally:
        os.close(fd)


def windows(p: Profile) -> Path:
    """The locks of the ReelForge windows showing a profile, one each (dashboard/service.py takes its own when it opens
    on the profile; the system lets go of it when the window closes, even in a crash)."""
    return p.data / WINDOWS


def shown(p: Profile) -> bool:
    """Whether a ReelForge window is showing this profile right now (or one that switched away from it is still
    finishing a stats read)."""
    try:
        locks = list(windows(p).glob("*.lock"))
    except OSError:
        return False
    return any(held(lock) for lock in locks)


def reading(p: Profile) -> bool:
    """Whether a ReelForge (a window or the hourly stats job) is reading this profile's stats right now."""
    return held(p.data / READ_LOCK)


def wait_for_read(p: Profile, seconds: float = 90, say=None) -> bool:
    """Give a read of this profile's stats under way the time to finish (it has them open, so its folder can't move
    until it's done), saying so once if it has to wait. False: it's still reading after `seconds`."""
    end, told = time.monotonic() + seconds, False
    while reading(p):
        if time.monotonic() >= end:
            return False
        if say is not None and not told:
            say(f"Waiting for {p.name}'s stats read to finish...")
            told = True
        time.sleep(1)
    return True


def size(path: Path) -> int:
    """The bytes in a folder (or a file), counted file by file."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for dirpath, _, names in os.walk(path):
        for name in names:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def _move(src: Path, dst: Path, wait: float) -> str | None:
    """Rename src to dst (the same drive, so nothing is copied), trying again for a few seconds while something has a
    file in it open. Returns what went wrong, or None."""
    end = time.monotonic() + wait
    while True:
        try:
            os.rename(src, dst)
            return None
        except OSError as e:
            if time.monotonic() >= end:
                return e.strerror or str(e)
            time.sleep(0.5)


def _free(folder: Path, name: str, sep: str) -> Path:
    """folder/name, or name with 2, 3 ... after sep, so nothing already there is replaced."""
    n, candidate = 1, folder / name
    while candidate.exists():
        n += 1
        candidate = folder / f"{name}{sep}{n}"
    return candidate


@dataclass(frozen=True)
class Deleted:
    """A deleted profile, kept whole in backups/deleted-profile-<its folder>-<date>/ until restore() puts it back."""
    backup: Path   # backups/deleted-profile-<its folder>-<date>: the folder the window and the commands name it by

    @property
    def folder(self) -> Path | None:
        """The profile's folder as it was in profiles/ (the backup's folder with a profile.toml in it)."""
        try:
            return next((d for d in sorted(self.backup.iterdir()) if (d / MARK).is_file()), None)
        except OSError:
            return None

    @property
    def name(self) -> str:
        folder = self.folder
        return Profile(folder).name if folder is not None else self.backup.name

    @property
    def where(self) -> str:
        """Where it's kept, from the ReelForge folder: backups/deleted-profile-<its folder>-<date>."""
        return os.path.join(backups().name, self.backup.name)

    @property
    def when(self) -> datetime | None:
        """When it was deleted: the date at the end of its backup's name."""
        m = _STAMP.search(self.backup.name)
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d-%H%M%S") if m else None
        except ValueError:
            return None


def deleted() -> list[Deleted]:
    """The profiles deleted and kept in backups/, the newest first."""
    try:
        found = [Deleted(d) for d in backups().iterdir() if d.is_dir() and d.name.startswith(DELETED + "-")]
    except OSError:
        return []
    found = [d for d in found if d.folder is not None]
    return sorted(found, key=lambda d: (d.when or datetime.min, d.backup.name), reverse=True)


def find_deleted(word: str) -> Deleted | None:
    """A deleted profile, as typed after `reelforge profiles restore`: its number in their list (1 is the newest), its
    name (any case, the newest one called that), or its backup's folder name."""
    word = (word or "").strip()
    gone = deleted()
    if word.isdigit():
        n = int(word)
        return gone[n - 1] if 1 <= n <= len(gone) else None
    low = word.casefold()
    return next((d for d in gone if low in (d.name.casefold(), d.backup.name.casefold())), None)


def delete(p: Profile, wait: float = 10) -> Deleted:
    """Take a channel you added out of ReelForge: its folder moves whole (accounts, log-ins, stats, notifications,
    settings, your AI's notes, its videos) into backups/deleted-profile-<its folder>-<date>/ in the ReelForge folder,
    on the same drive, so nothing is copied and nothing is deleted. All or nothing: it moves, or nothing changes.
    Raises ValueError when it can't be deleted (the first profile, one a window is showing or a stats read is reading:
    wait_for_read first) and OSError when its folder couldn't be moved (a file in it open somewhere: nothing changed)."""
    if p.main or not (p.folder / MARK).is_file():
        raise ValueError(f"{p.name} is the ReelForge folder's own channel, which can't be deleted." if p.main else
                         f"{p.folder} isn't a profile.")
    if shown(p):
        raise ValueError(f"{p.name} is open in a ReelForge window.")
    if reading(p):
        raise ValueError(f"{p.name}'s stats are being read.")
    home = _free(backups(), f"{DELETED}-{p.folder.name}-{datetime.now():%Y-%m-%d-%H%M%S}", " ")
    home.mkdir(parents=True)
    err = _move(p.folder, home / p.folder.name, wait)
    if err:
        try:
            home.rmdir()
        except OSError:
            pass
        raise OSError(f"{p.name}'s folder couldn't be moved ({err}), so nothing changed.")
    try:
        (home / "README.txt").write_text(
            f"ReelForge deleted the profile {p.name} on {datetime.now():%d %B %Y at %H:%M}, and kept it here whole: "
            f"its accounts, log-ins, stats, notifications, settings, your AI's notes on it and its videos.\n\n"
            f"To bring it back, click Restore beside it on ReelForge's Settings tab, or run: reelforge profiles "
            f"restore \"{p.name}\"\nThe log-ins in {p.folder.name}/dashboard/data/browser are your own: delete this "
            "folder once you're sure you don't need it.\n", encoding="utf-8")
    except OSError:
        pass  # a note for you, nothing restore needs
    return Deleted(home)


def restore(d: Deleted, wait: float = 10) -> Profile:
    """Put a deleted profile back in profiles/, in its old folder (with -2, -3 ... when a new profile has that
    name), with everything it had. Raises ValueError when another profile has its name, OSError when its folder
    couldn't be moved (nothing changed)."""
    folder = d.folder
    if folder is None:
        raise ValueError(f"{d.backup} has no profile in it.")
    name = Profile(folder).name
    if other := taken(name):
        raise ValueError(f"You already have a profile called {other.name}: delete that one first (it's kept too), "
                         "then restore this one.")
    FOLDER.mkdir(parents=True, exist_ok=True)
    target = _free(FOLDER, folder.name, "-")
    err = _move(folder, target, wait)
    if err:
        raise OSError(f"{name}'s folder couldn't be moved back ({err}), so nothing changed.")
    try:
        (d.backup / "README.txt").unlink(missing_ok=True)
        d.backup.rmdir()
    except OSError:
        pass  # something else was left in the backup: it stays, with nothing ReelForge lists
    return Profile(target)
