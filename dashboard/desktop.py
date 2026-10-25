"""Small helpers for manual uploading: clipboard, Recycle Bin / Trash, Explorer / Finder, browser.

Windows talks to the system directly. macOS uses its own commands (pbcopy, trash, open). Linux uses the desktop's
standards: wl-copy, xclip or xsel for the clipboard, gio or the freedesktop.org trash folder, and the file
manager's ShowItems call (Files, Dolphin, Nemo, Thunar and Caja all answer it)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
FILES = "Explorer" if WINDOWS else "Finder" if MAC else "the file manager"    # what shows your files, for messages
FILES_WINDOW = "the Explorer window" if WINDOWS else "the Finder window" if MAC else "the file manager's window"
BIN = "Recycle Bin" if WINDOWS else "Trash"

# Where each platform's own upload screen lives. Instagram has no direct link: click "+ Create" there.
UPLOAD_PAGES = {
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "youtube": "https://www.youtube.com/upload",
    "instagram": "https://www.instagram.com/",
    "x": "https://x.com/compose/post",
}


def copy(text: str) -> bool:
    """Put text on the clipboard. Returns False if that isn't possible (no clipboard tool, locked clipboard); the
    app then asks the terminal to do it."""
    if WINDOWS:
        return _windows_copy(text)
    if MAC:
        tools = [["pbcopy"]]
    else:
        tools = ([["wl-copy"]] if os.environ.get("WAYLAND_DISPLAY") else []) + [
            ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in tools:
        if not shutil.which(cmd[0]):
            continue
        try:
            # These tools stay behind to hand the text over when it's pasted, so nothing waits on their output.
            r = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, env={**os.environ, "LC_CTYPE": "UTF-8"})
            if r.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def _windows_copy(text: str) -> bool:
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-16-le") + b"\0\0"
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # the clipboard owns the memory now
    finally:
        user32.CloseClipboard()


def recycle(path: Path) -> bool:
    """Move a file to the Recycle Bin / Trash (so it can be restored). Returns whether it worked."""
    path = Path(path).absolute()
    if WINDOWS:
        return _windows_recycle(path)
    if MAC:
        if Path("/usr/bin/trash").exists():          # macOS 15 and newer: the Trash's own Put Back works too
            return subprocess.run(["/usr/bin/trash", str(path)], capture_output=True).returncode == 0
        return _move_into(path, Path.home() / ".Trash")
    if shutil.which("gio"):                          # GNOME's tool: handles other drives' trash folders too
        if subprocess.run(["gio", "trash", str(path)], capture_output=True).returncode == 0:
            return True
    return freedesktop_trash(path)


def _windows_recycle(path: Path) -> bool:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    FOF_WANTNUKEWARNING = 0x4000  # ask first if the file can't go to the Recycle Bin and would be deleted for good
    # pFrom is a list ending in two NULs; ctypes adds the second.
    op = SHFILEOPSTRUCTW(None, FO_DELETE, str(path) + "\0", None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING,
                         False, None, None)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def _free_name(folder: Path, name: str, taken=lambda n: False) -> str:
    """name, or name with a number before its extension, so it doesn't replace anything in folder."""
    stem, dot, ext = name.rpartition(".") if "." in name.lstrip(".") else (name, "", "")
    n, candidate = 1, name
    while (folder / candidate).exists() or taken(candidate):
        n += 1
        candidate = f"{stem} {n}{dot}{ext}"
    return candidate


def _move_into(path: Path, folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        os.rename(path, folder / _free_name(folder, path.name))
        return True
    except OSError:
        return False


def freedesktop_trash(path: Path, trash: Path | None = None) -> bool:
    """The freedesktop.org trash: the file goes in ~/.local/share/Trash/files with a note in info/ saying where it
    came from, which every Linux file manager reads to put it back. Only for files on the same drive as home (others
    stay where they are, and this returns False)."""
    trash = trash or Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")) / "Trash"
    files, info = trash / "files", trash / "info"
    try:
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        name = _free_name(files, path.name, lambda n: (info / f"{n}.trashinfo").exists())
        note = info / f"{name}.trashinfo"
        with open(note, "x", encoding="utf-8") as f:    # "x": another program can't take the same name meanwhile
            f.write(f"[Trash Info]\nPath={quote(str(path))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    except OSError:
        return False
    try:
        os.rename(path, files / name)
        return True
    except OSError:
        note.unlink(missing_ok=True)
        return False


def reveal(path: Path) -> None:
    """Show the file selected in Explorer / Finder / the file manager, ready to drag into an upload page."""
    path = Path(path).resolve()
    if WINDOWS:
        # Explorer only understands /select,"<path>" with the quotes around the path alone; a list
        # argument would quote the whole thing and Explorer would open Documents instead.
        subprocess.Popen(f'explorer /select,"{path}"')
    elif MAC:
        subprocess.Popen(["open", "-R", str(path)])
    else:
        threading.Thread(target=_linux_reveal, args=(path,), daemon=True).start()


def _linux_reveal(path: Path) -> None:
    """Ask the file manager to show the file selected; one that can't gets its folder opened instead."""
    if shutil.which("dbus-send"):
        try:
            r = subprocess.run(["dbus-send", "--session", "--print-reply", "--reply-timeout=4000",
                                "--dest=org.freedesktop.FileManager1", "--type=method_call",
                                "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                                f"array:string:{path.as_uri()}", "string:"], capture_output=True, timeout=6)
            if r.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    open_url(path.parent.as_uri())


def open_url(url: str) -> None:
    import webbrowser  # imported on first use: it's slow to load and only needed on a click

    webbrowser.open(url)


def open_upload_page(platform: str) -> None:
    open_url(UPLOAD_PAGES[platform])


def profile_url(platform: str, handle: str) -> str:
    """Your public profile page, for a handle without the @."""
    return {
        "tiktok": f"https://www.tiktok.com/@{handle}",
        "youtube": f"https://www.youtube.com/@{handle}",
        "instagram": f"https://www.instagram.com/{handle}/",
        "x": f"https://x.com/{handle}",
    }[platform]
