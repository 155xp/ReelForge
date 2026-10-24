"""The reelforge command: type `reelforge` in any terminal to open ReelForge.

  python -m studio command on|off      (setup and the Windows installer turn it on for you)
  python -m studio command             is it on?

Windows: puts this folder's bin\\ on your user PATH (no admin rights needed; terminal windows opened afterwards see
it). macOS/Linux: links bin/reelforge into ~/.local/bin and, if that folder isn't on your PATH yet, adds it in your
shell's startup file (~/.zshrc, ~/.bashrc or ~/.profile).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import paths as P

BIN = P.ROOT / "bin"
MARK = "# added by ReelForge"


def _dry() -> bool:
    """STUDIO_DRY_SYSTEM=1 (tests) or a test copy: say what would happen without changing PATH or files outside
    the kit."""
    return P.dry_system()


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(p.strip().strip('"')))).rstrip("\\/")


# ---------------------------------------------------------------- Windows: the user PATH in the registry

def _win_user_path() -> tuple[str, int]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as k:
            value, kind = winreg.QueryValueEx(k, "Path")
            return str(value), kind
    except FileNotFoundError:
        return "", winreg.REG_EXPAND_SZ


def _win_set_user_path(value: str, kind: int) -> None:
    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Path", 0, kind, value)
    # tell Explorer (and the terminals it starts from now on) that the environment changed
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x2, 3000, ctypes.byref(result))


# ---------------------------------------------------------------- macOS / Linux: ~/.local/bin

def _link() -> Path:
    return Path.home() / ".local" / "bin" / "reelforge"


def _rc_file() -> Path:
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    if shell.endswith("zsh") or (P.MAC and not shell):
        return home / ".zshrc"
    if shell.endswith("bash"):
        return home / ".bashrc"
    return home / ".profile"


def _on_path(folder: Path) -> bool:
    return any(_norm(p) == _norm(str(folder)) for p in os.environ.get("PATH", "").split(os.pathsep) if p)


# ---------------------------------------------------------------- the commands

def status() -> str:
    """'on' when `reelforge` in a new terminal opens this copy of ReelForge, else 'off'."""
    if P.WINDOWS:
        value, _ = _win_user_path()
        return "on" if _norm(str(BIN)) in {_norm(e) for e in value.split(";") if e.strip()} else "off"
    link = _link()
    try:
        return "on" if link.is_symlink() and link.resolve() == (BIN / "reelforge").resolve() else "off"
    except OSError:
        return "off"


def enable() -> str:
    """Turn the command on. Returns a sentence saying what happened."""
    if P.test_copy():
        return "Left alone in a test copy: reelforge still opens your main ReelForge."
    if _dry():
        return "(dry run) would add the reelforge command"
    if P.WINDOWS:
        value, kind = _win_user_path()
        entries = [e for e in value.split(";") if e.strip()]
        if _norm(str(BIN)) not in {_norm(e) for e in entries}:
            _win_set_user_path(";".join([*entries, str(BIN)]), kind)
        return "Type reelforge in any new terminal window to open ReelForge."
    script = BIN / "reelforge"
    script.chmod(0o755)
    link = _link()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        ours = link.is_symlink() and link.resolve() == script.resolve()
        if not ours:
            return f"There's already a reelforge command at {link}; remove it and run this again to use this copy."
        link.unlink()
    link.symlink_to(script)
    if not _on_path(link.parent):
        rc = _rc_file()
        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if MARK not in text:
            with rc.open("a", encoding="utf-8") as f:
                f.write(f'\nexport PATH="$HOME/.local/bin:$PATH"  {MARK}\n')
        return f"Open a new terminal window and type reelforge (~/.local/bin was added to your PATH in {rc.name})."
    return "Type reelforge in any terminal to open ReelForge."


def disable() -> str:
    if P.test_copy():
        return "Left alone in a test copy: it never changes the reelforge command."
    if _dry():
        return "(dry run) would remove the reelforge command"
    if P.WINDOWS:
        value, kind = _win_user_path()
        entries = [e for e in value.split(";") if e.strip()]
        keep = [e for e in entries if _norm(e) != _norm(str(BIN))]
        if keep != entries:
            _win_set_user_path(";".join(keep), kind)
        return "The reelforge command is off (new terminal windows won't find it)."
    link = _link()
    try:
        if link.is_symlink() and link.resolve() == (BIN / "reelforge").resolve():
            link.unlink()
    except OSError:
        pass
    return "The reelforge command is off."


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "on":
        print(enable())
    elif cmd == "off":
        print(disable())
    elif cmd == "status":
        print(f"The reelforge command: {status()}")
    else:
        print("usage: reelforge command [on|off]")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
