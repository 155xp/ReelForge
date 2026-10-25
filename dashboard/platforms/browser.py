"""Stats read through ReelForge's own browser.

ReelForge drives a browser already on your computer (Edge on Windows, Chrome on macOS and Linux: studio/browsers.py
has the order) with a profile of its own in data/browser, separate from your normal browsing. You log in to
Instagram and X there once, from the Accounts tab; after that ReelForge opens your profile in the
background about once an hour and reads the numbers the page loads, the same ones you'd
see. TikTok works without logging in. Nothing is posted, liked or followed.
"""

from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from studio import browsers

from .. import config
from .base import Account, PlatformError, Post, first_line

PROFILE = config.DATA_DIR / "browser"
CHOSEN = PROFILE / "reelforge-browser.txt"   # the browser this profile belongs to (studio.browsers.key)
LOGIN_URLS = {"instagram": "https://www.instagram.com/accounts/login/", "x": "https://x.com/i/flow/login"}
SESSION_COOKIES = {"instagram": ("instagram.com", "sessionid"), "x": ("x.com", "auth_token")}

_lock = threading.Lock()  # a browser profile can only be open once at a time


def chosen() -> browsers.Browser | None:
    """The browser ReelForge reads stats with: the one its profile was made with while that's still installed."""
    try:
        remembered = CHOSEN.read_text(encoding="utf-8").strip()
    except OSError:
        remembered = ""
    return browsers.find(remembered)


NAME = getattr(chosen(), "name", "Chromium")  # for messages: "Edge", "Chrome" or "Chromium" (setup gets one)


def available() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def logged_in(platform: str) -> bool:
    """Whether you've logged in to this platform in ReelForge's browser (as far as ReelForge knows)."""
    return config.get_token(f"browser:{platform}") is not None


def forget(platform: str) -> None:
    config.set_token(f"browser:{platform}", None)


@contextmanager
def _browser(headless: bool = True):
    if not available():
        raise PlatformError("Browser stats need Playwright: run setup again to install it.")
    b = chosen()
    if b is None:
        raise PlatformError("Browser stats need Chrome, Edge or Chromium: run setup again (reelforge setup) and it "
                            "downloads Chromium.")
    from playwright.sync_api import sync_playwright

    with _lock, sync_playwright() as pw:
        # The browser exits with code 21 when the profile is still held, e.g. by the previous read's browser
        # finishing up or by the hourly background refresh; give it a few seconds before giving up.
        for attempt in range(8):
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(PROFILE), executable_path=str(b.exe) if b.exe else None,
                    channel=None if b.exe else "chromium", headless=headless,
                    user_agent=browsers.user_agent(b) if headless else None,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 900} if headless else None,
                    no_viewport=not headless,
                )
                break
            except Exception as e:
                busy = "exitCode=21" in str(e)
                if busy and attempt < 7:
                    time.sleep(2.5)
                    continue
                if busy:
                    raise PlatformError("ReelForge's browser was busy with another read; it tries again next "
                                        "refresh.") from e
                raise PlatformError(f"Couldn't start {b.describe()}: {str(e).splitlines()[0]}") from e
        try:
            CHOSEN.write_text(browsers.key(b), encoding="utf-8")
        except OSError:
            pass
        try:
            yield ctx
        finally:
            ctx.close()


def _has_session(ctx, platform: str) -> bool:
    domain, name = SESSION_COOKIES[platform]
    return any(c["name"] == name and domain in c["domain"] for c in ctx.cookies())


def login(platform: str, timeout: float = 600) -> None:
    """Open a visible window of ReelForge's browser on the platform's login page and wait until you've logged in."""
    with _browser(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URLS[platform])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _has_session(ctx, platform):
                page.wait_for_timeout(3000)  # let the site finish setting cookies
                config.set_token(f"browser:{platform}", {"since": time.time()})
                return
            if not ctx.pages:
                break  # you closed the window
            time.sleep(1)
    raise PlatformError("The login window closed before you finished logging in.")


NAMES = {"instagram": "Instagram", "x": "X"}


def _logged_out(platform: str) -> PlatformError:
    """The session cookie is gone: ReelForge's browser really is logged out."""
    was = logged_in(platform)
    forget(platform)
    if was:
        return PlatformError(f"{NAMES[platform]} logged ReelForge's browser out. Log in again on the Accounts tab (5).",
                             needs_login=True)
    return PlatformError(f"Log in to {NAMES[platform]} once on the Accounts tab (5) so ReelForge can read your stats.",
                         needs_login=True)


def _sent_to_login(platform: str) -> PlatformError:
    """The site showed its login page although the session cookie is there. That can be a one-off, so ReelForge only
    forgets the login the second time in a row."""
    entry = config.get_token(f"browser:{platform}") or {}
    if entry.get("misses", 0) >= 1:
        return _logged_out(platform)
    config.set_token(f"browser:{platform}", {**entry, "misses": entry.get("misses", 0) + 1})
    return PlatformError(f"{NAMES[platform]} showed ReelForge's browser its login page; it tries again next refresh. "
                         "If it keeps happening, press Log in again on the Accounts tab (5).")


def _read_ok(platform: str) -> None:
    entry = config.get_token(f"browser:{platform}")
    if entry and entry.get("misses"):
        config.set_token(f"browser:{platform}", {**entry, "misses": 0})


def _count(value) -> int | None:
    """A count from a page, or None when the page didn't include it."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _walk(node):
    """Every dict inside a JSON tree."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


# --- TikTok (no login) -----------------------------------------------------------------------

def tiktok_profile_stats(page_html: str) -> dict | None:
    m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        return None
    detail = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
    return detail.get("userInfo", {}).get("stats")


def tiktok(handle: str) -> tuple[Account, list[Post]]:
    """Followers and totals, plus plays/likes/comments/shares/saves for each recent video."""
    with _browser() as ctx:
        page = ctx.new_page()
        items: dict[str, dict] = {}

        def on_response(resp):
            if "/api/post/item_list" in resp.url:
                try:
                    for it in json.loads(resp.text() or "{}").get("itemList") or []:
                        items[str(it["id"])] = it
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(f"https://www.tiktok.com/@{handle}", wait_until="domcontentloaded", timeout=45000)
        stats = tiktok_profile_stats(page.content())
        if stats and stats.get("videoCount"):
            # The video list arrives a moment after the page; stop once it has settled.
            seen, quiet = 0, 0
            for _ in range(15):
                page.wait_for_timeout(1000)
                quiet = quiet + 1 if len(items) == seen and items else 0
                seen = len(items)
                if quiet >= 2:
                    break
    if not stats:
        raise PlatformError(f"TikTok didn't load @{handle}'s profile (wrong handle, or a captcha); "
                            "it tries again next refresh.")

    posts = []
    for it in items.values():
        s = {**(it.get("stats") or {}), **{k: int(v) for k, v in (it.get("statsV2") or {}).items() if str(v).isdigit()}}
        posts.append(Post(
            post_id=str(it["id"]),
            title=first_line(it.get("desc")),
            url=f"https://www.tiktok.com/@{handle}/video/{it['id']}",
            published_at=int(it["createTime"]),
            views=_count(s.get("playCount")),
            likes=int(s.get("diggCount", 0)),
            comments=int(s.get("commentCount", 0)),
            shares=int(s.get("shareCount", 0)),
            saves=int(s["collectCount"]) if "collectCount" in s else None,
        ))
    return Account(handle=f"@{handle}", followers=stats.get("followerCount"), likes=stats.get("heartCount"),
                   posts=stats.get("videoCount")), posts


# --- Instagram (log in once) -----------------------------------------------------------------

# Instagram's own profile page loads these queries (identified by their x-fb-friendly-name header).
IG_QUERIES = ("PolarisProfilePageContentQuery", "PolarisProfilePostsQuery", "PolarisProfileReelsTabContentQuery")
IG_EPOCH_MS = 1314220021721  # media ids carry their upload time: (pk >> 23) + this epoch, in ms


def instagram(handle: str) -> tuple[Account, list[Post]]:
    """Open the Reels tab of your profile, as you would, and read what the page loads."""
    with _browser() as ctx:
        if not _has_session(ctx, "instagram"):
            raise _logged_out("instagram")
        page = ctx.new_page()
        got: dict[str, list] = {q: [] for q in IG_QUERIES}

        def on_response(resp):
            name = resp.request.headers.get("x-fb-friendly-name", "")
            if name in got:
                try:
                    got[name].append(resp.json())
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(f"https://www.instagram.com/{handle}/reels/", wait_until="domcontentloaded", timeout=45000)
        for _ in range(15):
            page.wait_for_timeout(1000)
            if got["PolarisProfilePageContentQuery"] and got["PolarisProfileReelsTabContentQuery"]:
                break
        # The Reels tab carries no captions; the profile's main grid does.
        if "/accounts/login" not in page.url and not got["PolarisProfilePostsQuery"]:
            page.goto(f"https://www.instagram.com/{handle}/", wait_until="domcontentloaded", timeout=45000)
            for _ in range(10):
                page.wait_for_timeout(1000)
                if got["PolarisProfilePostsQuery"]:
                    break
        on_login_page = "/accounts/login" in page.url
        challenge = "/challenge" in page.url or "/checkpoint" in page.url
    if challenge:
        raise PlatformError("Instagram wants to check it's you: press Log in again on the Accounts tab (5) and "
                            "follow its steps in the window that opens.")
    if on_login_page:
        raise _sent_to_login("instagram")
    result = parse_instagram(got, handle)
    _read_ok("instagram")
    return result


def parse_instagram(got: dict[str, list], handle: str) -> tuple[Account, list[Post]]:
    """Profile query -> followers; posts tab -> dates and captions; Reels tab -> play counts."""
    user = next((d for d in _walk(got.get("PolarisProfilePageContentQuery", []))
                 if "follower_count" in d and str(d.get("username", handle)).lower() == handle.lower()), None)
    if user is None:
        raise PlatformError(f"Instagram didn't load @{handle}'s profile (wrong handle?); it tries again next refresh.")

    def media(query: str) -> dict[str, dict]:
        return {str(d["pk"]): d for d in _walk(got.get(query, []))
                if "pk" in d and "code" in d and "like_count" in d and "media_type" in d}

    posts_tab, reels_tab = media("PolarisProfilePostsQuery"), media("PolarisProfileReelsTabContentQuery")
    posts = []
    for pk in dict.fromkeys([*reels_tab, *posts_tab]):  # every reel, newest first, without repeats
        m = {**posts_tab.get(pk, {}), **{k: v for k, v in reels_tab.get(pk, {}).items() if v is not None}}
        if m.get("media_type") != 2 and m.get("product_type") != "clips":
            continue  # photos and carousels aren't episodes
        taken = m.get("taken_at") or ((int(pk) >> 23) + IG_EPOCH_MS) // 1000
        posts.append(Post(
            post_id=pk,
            title=first_line((m.get("caption") or {}).get("text")),
            url=f"https://www.instagram.com/reel/{m['code']}/",
            published_at=int(taken),
            views=_count(m.get("play_count") or m.get("ig_play_count") or m.get("view_count")),
            likes=int(m.get("like_count") or 0),
            comments=int(m.get("comment_count") or 0),
            shares=m.get("reshare_count"),
        ))
    return Account(handle=f"@{handle}", followers=user.get("follower_count"), posts=user.get("media_count")), posts


# --- X (log in once) -------------------------------------------------------------------------

X_TIMELINES = ("UserOriginalsTimeline", "UserTweets")  # X has used both names for the profile's posts


def _x_tweet(d: dict) -> dict | None:
    if d.get("__typename") == "TweetWithVisibilityResults":
        d = d.get("tweet") or {}
    legacy = d.get("legacy")
    if not isinstance(legacy, dict) or "id_str" not in legacy or "full_text" not in legacy:
        return None
    return {**legacy, "_views": (d.get("views") or {}).get("count")}


def x(handle: str) -> tuple[Account, list[Post]]:
    with _browser() as ctx:
        if not _has_session(ctx, "x"):
            raise _logged_out("x")
        page = ctx.new_page()
        got: dict[str, list] = {"UserByScreenName": [], **{t: [] for t in X_TIMELINES}}

        def on_response(resp):
            if "/graphql/" not in resp.url:
                return
            op = resp.url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            if op in got:
                try:
                    got[op].append(resp.json())
                except Exception:
                    pass

        def timeline_loaded() -> bool:
            return any(got[t] for t in X_TIMELINES)

        page.on("response", on_response)
        page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=45000)
        for _ in range(20):
            page.wait_for_timeout(1000)
            if got["UserByScreenName"] and timeline_loaded():
                break
        if timeline_loaded():
            page.mouse.wheel(0, 6000)  # one scroll loads the next ~20 posts
            page.wait_for_timeout(2500)
        on_login_page = "/login" in page.url or "/i/flow" in page.url

    if on_login_page:
        raise _sent_to_login("x")
    result = parse_x(got, handle)
    _read_ok("x")
    return result


def parse_x(got: dict[str, list], handle: str) -> tuple[Account, list[Post]]:
    """Turn captured profile and timeline responses into an account and its video posts."""
    user = next((d for d in _walk(got.get("UserByScreenName", []))
                 if "relationship_counts" in d or (isinstance(d.get("legacy"), dict) and "followers_count" in d["legacy"])),
                None)
    if user is None:
        raise PlatformError(f"X didn't load @{handle}'s profile; it tries again next refresh.")
    legacy_user = user.get("legacy") if isinstance(user.get("legacy"), dict) else {}
    followers = (user.get("relationship_counts") or {}).get("followers", legacy_user.get("followers_count"))
    user_id = user.get("rest_id")

    posts, seen = [], set()
    for d in _walk([got.get(t, []) for t in X_TIMELINES]):
        t = _x_tweet(d)
        if not t or t["id_str"] in seen or (user_id and t.get("user_id_str") != user_id):
            continue
        seen.add(t["id_str"])
        if "retweeted_status_result" in t:
            continue
        media = ((t.get("extended_entities") or {}).get("media") or []) + ((t.get("entities") or {}).get("media") or [])
        if not any(m.get("type") in ("video", "animated_gif") for m in media):
            continue  # only video posts are episodes
        posts.append(Post(
            post_id=t["id_str"],
            title=first_line(t["full_text"]),
            url=f"https://x.com/{handle}/status/{t['id_str']}",
            published_at=datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").isoformat(),
            views=_count(t["_views"]),
            likes=t.get("favorite_count", 0),
            comments=t.get("reply_count", 0),
            shares=t.get("retweet_count", 0) + t.get("quote_count", 0),
            saves=t.get("bookmark_count"),
        ))
    return Account(handle=f"@{handle}", followers=followers, posts=legacy_user.get("statuses_count")), posts
