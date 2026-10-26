"""Making the accounts a channel needs, for creators starting from scratch, and reading the @handle they end up with.

Onboarding's "Your accounts" step and the ReelForge window's Accounts tab show these guides: a few steps, and a button
that opens the platform's own sign-up page in your usual browser. ReelForge never makes an account itself, fills in a
sign-up form or sees a password: you sign up on the site, then type your new @handle into ReelForge.

A second channel (once ReelForge has more than one profile) signs up in a private window of your browser. You're
probably logged in to your other channel there, and most sign-up pages skip straight to the account you're logged in
to; a private window starts with nothing logged in, so you sign up fresh and your other channel stays logged in. The
pages opened while it's open share it, so the Gmail you make first signs you in to the rest.
"""

from __future__ import annotations

import os
import plistlib
import re
import shlex
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"


@dataclass(frozen=True)
class Guide:
    key: str
    title: str          # the guide's heading
    why: str            # a line on what it's for
    url: str            # the official sign-up page
    button: str         # the button that opens it
    steps: tuple[str, ...]  # what to do there; {like}, {both} and {gmail} become examples made from the channel's name
    longest: int = 30   # the longest @handle the platform takes

    @property
    def logs_in(self) -> bool:
        """Instagram and X also need one log-in in ReelForge's own browser before it can read your stats."""
        return self.key in ("instagram", "x")

    def steps_for(self, channel: str = "") -> list[str]:
        """Its steps, with examples made from the channel's name when it has one (", like @coolepicfacts")."""
        s = suggest(channel, self.longest)
        return [step.format(like=f", like {s['handle']}" if s else "",
                            both=f", like {channel.strip()} and {s['handle']}" if s else "",
                            gmail=s["gmail"] if s else "nightphysics@gmail.com") for step in self.steps]


GMAIL = Guide(
    "gmail", "Make a Gmail for your channel",
    "One Gmail just for your channel is your YouTube login, and TikTok, Instagram and X can sign up with the same "
    "email, so the whole channel lives on one address, apart from your personal accounts.",
    "https://accounts.google.com/signup", "Open Google sign-up",
    ("Name it after your channel, and pick an address to match, like {gmail}.",
     "Google may text your phone a code to check it's you. Keep the password somewhere safe.",
     "Then make your accounts with it: YouTube first, then the others."),
)

GUIDES = {
    "tiktok": Guide(
        "tiktok", "Make your TikTok account", "Sign up on TikTok with your channel's Gmail.",
        "https://www.tiktok.com/signup", "Open TikTok sign-up",
        ("Sign up with your channel's Gmail (Use phone or email), or Continue with Google.",
         "Pick a username that matches your channel{like}: that's your @handle. You can change it later in Edit "
         "profile."), longest=24),
    "youtube": Guide(
        "youtube", "Make your YouTube channel", "Your channel's Gmail is all YouTube needs.",
        "https://www.youtube.com/create_channel", "Open YouTube",
        ("Sign in with your channel's Gmail.",
         "YouTube asks for a name and a handle for your channel: use your channel's name for both{both}.")),
    "instagram": Guide(
        "instagram", "Make your Instagram account", "Sign up on Instagram with your channel's Gmail.",
        "https://www.instagram.com/accounts/emailsignup/", "Open Instagram sign-up",
        ("Sign up with your channel's Gmail.",
         "Pick a username that matches your channel{like}: that's your @handle.")),
    "x": Guide(
        "x", "Make your X account", "Sign up on X with your channel's Gmail.",
        "https://x.com/i/flow/signup", "Open X sign-up",
        ("Sign up with your channel's Gmail, or Sign up with Google.",
         "Pick a username that matches your channel{like}: that's your @handle."), longest=15),
}

# A profile's address, for a handle pasted as a link: tiktok.com/@name, youtube.com/@name, instagram.com/name,
# x.com/name (or twitter.com/name).
_LINK = re.compile(r"^(?:https?://)?(?:[\w-]+\.)*(?:tiktok|youtube|instagram|x|twitter)\.com/@?([^/?#\s]+)", re.I)
_HANDLE = re.compile(r"^[A-Za-z0-9._-]{1,30}$")
_NOT_PROFILES = {"channel", "c", "user", "watch", "shorts", "p", "reel", "reels", "video", "i", "home", "explore"}


def handle_from(text: str) -> str:
    """What you typed (@name, name, or your profile's link) -> "@name", or "" for nothing. Raises ValueError, with a
    message to show, for anything else (a link to a video, or to a YouTube channel by its ID, isn't a handle)."""
    text = (text or "").strip()
    if not text:
        return ""
    link = _LINK.match(text)
    if link:
        if link.group(1).lower() in _NOT_PROFILES:
            raise ValueError("That link isn't your profile: type your @handle instead, like @yourchannel.")
        text = link.group(1)
    name = text.lstrip("@").strip()
    if not _HANDLE.match(name):
        raise ValueError("That isn't a handle: use letters, numbers, dots, dashes and underscores, like "
                         "@yourchannel.")
    return "@" + name


def suggest(channel: str, longest: int = 30) -> dict[str, str]:
    """What a channel's accounts could be called, made from its name: {"gmail": "coolepicfacts@gmail.com", "handle":
    "@coolepicfacts"} for Cool Epic Facts (as many of its words as fit the platform's longest handle), or {} for no
    name yet. Whether one's still free, the platform says when you sign up."""
    plain = unicodedata.normalize("NFKD", channel or "").encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", plain)
    if not words:
        return {}

    def fit(most: int) -> str:
        out = ""
        for w in words:
            if len(out + w) > most:
                break
            out += w
        return out or words[0][:most]

    gmail = fit(30)
    if len(gmail) < 6:  # Google wants 6 to 30 characters
        gmail += "videos"
    return {"gmail": gmail + "@gmail.com", "handle": "@" + fit(longest)}


# ---------------------------------------------------------------- what a guide shows, and opening its page

def _them(others: Sequence[str]) -> tuple[str, str]:
    """The other channels (a name each, "" for one without a name yet), and the verb that goes with them:
    ("Rendered Wrong", "stays")."""
    names = [n for n in others if n]
    if len(others) == 1:
        return (names[0] if names else "your other channel"), "stays"
    if len(others) == 2 and len(names) == 2:
        return f"{names[0]} and {names[1]}", "stay"
    return "your other channels", "stay"


def private_name(others: Sequence[str]) -> str:
    """The browser a second channel's sign-up pages open a private window of ("Chrome"); "" without other channels, or
    with a browser ReelForge can't open a private window of."""
    browser = private_browser() if others else None
    return browser.name if browser else ""


def where(others: Sequence[str]) -> str:
    """How a second channel's sign-up pages open, to put in a sentence: "in a private Chrome window, so you sign up
    fresh while Rendered Wrong stays logged in", or "" (see private_name)."""
    name = private_name(others)
    if not name:
        return ""
    them, verb = _them(others)
    return f"in a private {name} window, so you sign up fresh while {them} {verb} logged in"


def guide_view(key: str, channel: str = "", others: Sequence[str] = ()) -> dict:
    """A guide's dialog ("gmail" for the Gmail), up to the screen's own last step: its title, why, its steps, the
    button and whether it's an account (with a box for the @handle you end up with). channel: the channel's name, for
    the examples; others: the names of the other channels, whose accounts are probably logged in in your browser (a
    second channel signs up in a private window)."""
    g = GMAIL if key == "gmail" else GUIDES[key]
    how = where(others)
    if how:
        first = f"Press {g.button}: it opens {how}."
    elif others:
        them, _ = _them(others)
        first = (f"Press {g.button}: the page opens in your browser. Logged in to {them} there? Log out first, or "
                 "open the page in a private window.")
    else:
        first = f"Press {g.button}: the page opens in your browser."
    steps = [first, *g.steps_for(channel)]
    if how and g.key == "gmail":
        steps.append("Keep the private window open until you've made them all: they open in it too, signed in to "
                     "this Gmail.")
    return {"key": g.key, "title": g.title, "why": g.why, "steps": steps, "button": f"{g.button} →",
            "account": g.key != "gmail"}


def open_guide(key: str, others: Sequence[str] = ()) -> str:
    """Open a guide's sign-up page ("gmail" for the Gmail's): in a private window when there are other channels
    (others, as guide_view), else in your usual browser. What to say under its button."""
    url = (GMAIL if key == "gmail" else GUIDES[key]).url
    if others:
        name = open_private(url)
        if name:
            return f"Opened in a private {name} window. Come back here when you're done."
    open_page(url)
    if others:
        return "Opened in your browser: ReelForge can't open a private window of it. Come back here when you're done."
    return "Opened in your browser. Come back here when you're done."


def open_page(url: str) -> None:
    """A sign-up page in your usual browser (the tests put a stand-in here)."""
    import webbrowser

    webbrowser.open(url)


# ---------------------------------------------------------------- private windows

@dataclass(frozen=True)
class Private:
    """Your usual browser, as ReelForge opens a private window of it."""
    name: str                 # "Chrome", for messages
    command: tuple[str, ...]  # the program and its private-window switch; the page goes after them


# What a browser's program (or Linux desktop file) is called -> its name and the switch that opens a private window
# of it. The first match wins; only the program's own name is looked at, never the folders it's in.
_FAMILIES = (
    ("edge", "Edge", "--inprivate"),
    ("brave", "Brave", "--incognito"),
    ("vivaldi", "Vivaldi", "--incognito"),
    ("chromium", "Chromium", "--incognito"),
    ("chrome", "Chrome", "--incognito"),
    ("librewolf", "LibreWolf", "-private-window"),
    ("waterfox", "Waterfox", "-private-window"),
    ("floorp", "Floorp", "-private-window"),
    ("firefox", "Firefox", "-private-window"),
)
# A Mac browser's bundle id -> its app, its name and its switch: the Chrome-based ones, which take a switch from a
# second start (Safari has no way to be told, and a running Firefox ignores one).
_MAC_APPS = {
    "com.google.chrome": ("Google Chrome", "Chrome", "--incognito"),
    "com.microsoft.edgemac": ("Microsoft Edge", "Edge", "--inprivate"),
    "com.brave.browser": ("Brave Browser", "Brave", "--incognito"),
    "com.vivaldi.vivaldi": ("Vivaldi", "Vivaldi", "--incognito"),
    "org.chromium.chromium": ("Chromium", "Chromium", "--incognito"),
}


def _family(name: str) -> tuple[str, str] | None:
    low = name.lower()
    return next(((browser, switch) for word, browser, switch in _FAMILIES if word in low), None)


def from_command(command: str) -> Private | None:
    """A browser's open command, as Windows keeps it ("C:\\...\\chrome.exe" --single-argument %1) -> the private
    window ReelForge can open of it, or None for a browser it doesn't know."""
    m = re.match(r'\s*"([^"]+)"|\s*(\S+)', command or "")
    if not m:
        return None
    program = m.group(1) or m.group(2)
    known = _family(re.split(r"[\\/]", program)[-1].lower().removesuffix(".exe"))
    return Private(known[0], (program, known[1])) if known else None


def mac_default(handlers: list) -> str:
    """The bundle id of the Mac's browser for web links, from LaunchServices' handlers; Safari when none is picked."""
    for scheme in ("https", "http"):
        for h in handlers:
            if isinstance(h, dict) and h.get("LSHandlerURLScheme") == scheme and h.get("LSHandlerRoleAll"):
                return str(h["LSHandlerRoleAll"]).lower()
    return "com.apple.safari"


def from_bundle(bundle: str, folders: Sequence[Path] | None = None) -> Private | None:
    """A Mac browser's bundle id -> the private window ReelForge can open of it (with open -na, which a running browser
    takes too), or None."""
    known = _MAC_APPS.get(bundle.lower())
    if not known:
        return None
    app, name, switch = known
    for folder in folders if folders is not None else (Path("/Applications"), Path.home() / "Applications"):
        if (folder / f"{app}.app").is_dir():
            return Private(name, ("open", "-na", str(folder / f"{app}.app"), "--args", switch))
    return None


def from_desktop(desktop_id: str, text: str) -> Private | None:
    """A Linux browser's desktop file (its name, firefox.desktop, and what's in it) -> the private window ReelForge can
    open of it, or None. Snap and Flatpak browsers too: their Exec line starts them."""
    command, section = "", ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[Desktop Entry]" and line.startswith("Exec="):
            command = line[len("Exec="):]
            break
    try:
        words = [w for w in shlex.split(command) if not re.fullmatch(r"%[a-zA-Z]|@@u?", w)]  # %u, Flatpak's @@u
    except ValueError:
        return None
    if not words:
        return None
    known = _family(desktop_id.removesuffix(".desktop")) or _family(words[0].rsplit("/", 1)[-1])
    return Private(known[0], (*words, known[1])) if known else None


def _windows() -> Private | None:
    import winreg

    def read(root, path: str, name: str = "") -> str:
        try:
            with winreg.OpenKey(root, path) as key:
                return str(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return ""

    links = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations"
    for scheme in ("https", "http"):
        for choice in ("UserChoiceLatest", "UserChoice"):
            prog = read(winreg.HKEY_CURRENT_USER, rf"{links}\{scheme}\{choice}", "ProgId")
            found = prog and from_command(read(winreg.HKEY_CLASSES_ROOT, rf"{prog}\shell\open\command"))
            if found:
                return found
    # A browser ReelForge doesn't know: Edge, which every Windows PC has.
    bases = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    edge = next((p for b in bases if b and (p := Path(b, "Microsoft", "Edge", "Application", "msedge.exe")).is_file()),
                None)
    return Private("Edge", (str(edge), "--inprivate")) if edge else None


def _mac() -> Private | None:
    plist = Path.home() / "Library" / "Preferences" / "com.apple.LaunchServices" / \
        "com.apple.launchservices.secure.plist"
    try:
        handlers = plistlib.loads(plist.read_bytes()).get("LSHandlers", [])
    except (OSError, ValueError, plistlib.InvalidFileException):
        handlers = []
    return from_bundle(mac_default(handlers))


def _linux() -> Private | None:
    try:
        desktop = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not desktop.endswith(".desktop") or "/" in desktop:
        return None
    home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    shares = [home, *(Path(d) for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
                      if d), Path("/var/lib/snapd/desktop"), Path("/var/lib/flatpak/exports/share"),
              home / "flatpak" / "exports" / "share"]
    for share in shares:
        path = share / "applications" / desktop
        if path.is_file():
            return from_desktop(desktop, path.read_text(encoding="utf-8", errors="replace"))
    return None


_found: tuple[float, Private | None] | None = None  # the last look, and when (asking Linux takes a moment)


def private_browser() -> Private | None:
    """Your usual browser, when ReelForge knows how to open a private window of it: Chrome, Edge, Firefox, Brave,
    Vivaldi and Chromium (on a Mac, the Chrome-based ones). On Windows a browser it doesn't know gives way to Edge.
    None: the normal window, then. It looks again after a few minutes, in case you've picked another browser."""
    global _found
    if _found is not None and time.monotonic() - _found[0] < 300:
        return _found[1]
    try:
        browser = _windows() if WINDOWS else _mac() if MAC else _linux()
    except Exception:  # an odd registry, plist or desktop file
        browser = None
    _found = (time.monotonic(), browser)
    return browser


def launch(command: Sequence[str]) -> None:
    """Start a browser apart from ReelForge, so it stays open when ReelForge closes (the tests put a stand-in here)."""
    detach = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS
              else {"start_new_session": True})
    subprocess.Popen(list(command), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd=str(Path.home()), close_fds=True, **detach)


def open_private(url: str) -> str | None:
    """A page in a private window of your usual browser: the browser's name ("Chrome"), or None when ReelForge couldn't
    open one."""
    browser = private_browser()
    if browser is None:
        return None
    try:
        launch([*browser.command, url])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return browser.name
