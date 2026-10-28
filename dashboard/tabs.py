"""The ReelForge window's tabs: their ids, the order the ones along the top sit in, and the words that open the window
on one (reelforge publish, reelforge 2 ...). Standard library only, so the reelforge command can tell a tab from its
other commands without opening anything. The Stats tab's id is "totals": `reelforge stats` is the hourly job's command,
so `reelforge totals` opens the tab.

Publish isn't along the top with the others: it's the green button at the right of the header (u opens it too, and
so does reelforge publish), so it has no place in the order and no number. You pick the order of the rest on the
Settings tab (Tab order). Until you do, they sit in DEFAULT_ORDER: Overview, Videos, Compare, Stats, Accounts, Settings
and Updates. 1-7 open them in the order they're shown, in the window and after reelforge: reelforge 1 opens the one at
the far left. The order you pick is kept for every profile in the ReelForge folder's dashboard/data/tab-order.json,
which updates leave alone and a factory reset puts in its backup. Going back to the default order removes the file, so
a later version's default applies again. An order kept before Publish had its button just loses Publish."""

from __future__ import annotations

import json
from pathlib import Path

TAB_IDS = ("overview", "videos", "compare", "publish", "accounts", "updates", "settings", "totals")
PUBLISH = "publish"  # the green button at the right of the header opens it: it isn't one of the tabs along the top
DEFAULT_ORDER = ("overview", "videos", "compare", "totals", "accounts", "settings", "updates")  # every tab but Publish
HERE = Path(__file__).resolve().parent  # the window's code, with the first profile's data/ in it
# A tab's id, or another word for it. A number opens the tab in that place along the top (tab_for).
TABS: dict[str, str] = {
    **{tab: tab for tab in TAB_IDS},
    "home": "overview", "video": "videos", "post": "publish", "posts": "publish",
    "upload": "publish", "uploads": "publish", "account": "accounts", "login": "accounts", "logins": "accounts",
    "update": "updates", "setting": "settings", "preferences": "settings", "options": "settings", "total": "totals",
    "notifications": "overview", "notification": "overview", "alerts": "overview",
}
DRAWER_WORDS = {"notifications", "notification", "alerts"}
USAGE = (f"reelforge [1-{len(DEFAULT_ORDER)} | overview | videos | compare | publish | accounts | updates | settings | "
         "totals | notifications | refresh] [--demo]")


def order_file(folder: Path | None = None) -> Path:
    """Where the order you picked is kept: data/tab-order.json in the window's folder (the tests pass their own)."""
    return (folder or HERE) / "data" / "tab-order.json"


def tidy(tabs: object) -> tuple[str, ...]:
    """An order as the window or the file has it, made whole: each tab along the top once, in the order given, and any
    it leaves out (one a later version added) right after the tab it follows in the default order. Publish, which an
    order kept before it had its own button has in it, drops out with anything else that isn't along the top."""
    out: list[str] = []
    for tab in tabs if isinstance(tabs, (list, tuple)) else ():
        if tab in DEFAULT_ORDER and tab not in out:
            out.append(tab)
    for i, tab in enumerate(DEFAULT_ORDER):
        if tab not in out:
            before = next((t for t in reversed(DEFAULT_ORDER[:i]) if t in out), None)
            out.insert(out.index(before) + 1 if before else 0, tab)
    return tuple(out)


def order(folder: Path | None = None) -> tuple[str, ...]:
    """The tabs along the top from left to right: the order picked on the Settings tab, else the default."""
    try:
        kept = json.loads(order_file(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_ORDER
    return tidy(kept.get("order") if isinstance(kept, dict) else None)


def save_order(tabs: object, folder: Path | None = None) -> tuple[str, ...]:
    """Keep this order for every profile and return it, made whole. The default order (or none) removes the file
    instead. Raises OSError when it can't be written."""
    kept = tidy(tabs) if tabs else DEFAULT_ORDER
    path = order_file(folder)
    if kept == DEFAULT_ORDER:
        path.unlink(missing_ok=True)
        return kept
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"order": list(kept)}) + "\n", encoding="utf-8")
    tmp.replace(path)
    return kept


def tab_for(word: str) -> str | None:
    """The tab a word opens ("post" -> "publish"; "1" -> the one at the far left), or None if it isn't one."""
    word = (word or "").strip().lower()
    if word.isascii() and word.isdigit():
        tabs = order()
        return tabs[int(word) - 1] if 1 <= int(word) <= len(tabs) else None
    return TABS.get(word)
