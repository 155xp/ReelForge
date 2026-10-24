from .base import Account, Platform, PlatformError, Post, PublishItem
from .instagram import Instagram
from .tiktok import TikTok
from .x import X
from .youtube import YouTube

ORDER = (TikTok, YouTube, Instagram, X)


def build(cfg: dict) -> dict[str, Platform]:
    return {cls.key: cls(cfg.get(cls.key, {})) for cls in ORDER}


__all__ = ["Account", "Platform", "PlatformError", "Post", "PublishItem", "ORDER", "build"]
