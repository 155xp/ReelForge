"""The words that open the ReelForge window on a tab (reelforge 4, reelforge publish ...): no imports, so the
reelforge command can tell a tab from its other commands without opening anything. The Stats tab's id is "totals":
`reelforge stats` is the hourly job's command, so `reelforge 8` or `reelforge totals` opens the tab."""

from __future__ import annotations

TAB_IDS = ("overview", "videos", "compare", "publish", "accounts", "updates", "settings", "totals")
TABS: dict[str, str] = {
    **{str(i): tab for i, tab in enumerate(TAB_IDS, 1)},
    **{tab: tab for tab in TAB_IDS},
    "home": "overview", "video": "videos", "post": "publish", "posts": "publish",
    "upload": "publish", "uploads": "publish", "account": "accounts", "login": "accounts", "logins": "accounts",
    "update": "updates", "setting": "settings", "preferences": "settings", "options": "settings", "total": "totals",
    "notifications": "overview", "notification": "overview", "alerts": "overview",
}
DRAWER_WORDS = {"notifications", "notification", "alerts"}
USAGE = ("reelforge [1-8 | overview | videos | compare | publish | accounts | updates | settings | totals | "
         "notifications | refresh] [--demo]")


def tab_for(word: str) -> str | None:
    """The tab a word opens ("4", "publish", "post" -> "publish"), or None if it isn't one."""
    return TABS.get((word or "").strip().lower())
