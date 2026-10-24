"""Small Windows helpers for manual uploading: clipboard, Explorer, browser."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Where each platform's own upload screen lives. Instagram has no direct link: click "+ Create" there.
UPLOAD_PAGES = {
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "youtube": "https://www.youtube.com/upload",
    "instagram": "https://www.instagram.com/",
    "x": "https://x.com/compose/post",
}


def copy(text: str) -> bool:
    """Put text on the Windows clipboard. Returns False if that isn't possible (other OSes, locked clipboard)."""
    if sys.platform != "win32":
        return False
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
    """Move a file to the Recycle Bin (so it can be restored). Returns whether it worked."""
    if sys.platform != "win32":
        return False
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


def reveal(path: Path) -> None:
    """Open Explorer with the file selected, ready to drag into an upload page."""
    if sys.platform == "win32":
        # Explorer only understands /select,"<path>" with the quotes around the path alone; a list
        # argument would quote the whole thing and Explorer would open Documents instead.
        subprocess.Popen(f'explorer /select,"{Path(path).resolve()}"')
    else:
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
