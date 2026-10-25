"""Paths, config.toml and the local login store (which platforms you've logged in to in ReelForge's browser)."""

from __future__ import annotations

import json
import shutil
import threading
import tomllib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent     # the dashboard folder: its settings, data/ and videos/
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = APP_DIR / "config.toml"
DB_PATH = DATA_DIR / "stats.db"
TOKENS_PATH = DATA_DIR / "tokens.json"

PLATFORM_KEYS = ("tiktok", "youtube", "instagram", "x")

_tokens_lock = threading.Lock()


class ConfigError(Exception):
    """config.toml can't be read; the message says where."""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        shutil.copy(APP_DIR / "config.example.toml", CONFIG_PATH)
    try:
        with CONFIG_PATH.open("rb") as f:
            cfg = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{CONFIG_PATH.name} has a typo ({e}). Fix it in a text editor, or delete the file "
                          "and ReelForge makes a fresh one from config.example.toml.") from e
    for key in PLATFORM_KEYS:
        if not isinstance(cfg.get(key), dict):
            cfg[key] = {}
    return cfg


def resolve(path: str) -> Path:
    """Resolve a config path relative to the dashboard folder."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (APP_DIR / p).resolve()


def videos_dir(cfg: dict) -> Path:
    """Where you keep finished videos to upload (any .mp4 / .mov / .m4v in it is listed)."""
    return resolve(cfg.get("videos_dir", "videos"))


def episodes_dir(cfg: dict) -> Path:
    """The render pipeline's episodes folder, if you use it; ReelForge lists each episode's final/<id>.mp4."""
    return resolve(cfg.get("episodes_dir", "../episodes"))


def completed_dir(cfg: dict) -> Path:
    """Where the pipeline delivers finished cuts, one folder per video; ReelForge lists <folder>/*/<video>.mp4."""
    return resolve(cfg.get("completed_dir", "../completed videos"))


def _read_tokens() -> dict:
    if TOKENS_PATH.exists():
        try:
            data = json.loads(TOKENS_PATH.read_text("utf-8"))
        except (ValueError, OSError):
            return {}  # unreadable: treat as not logged in rather than crash
        return data if isinstance(data, dict) else {}
    return {}


def get_token(platform: str) -> dict | None:
    with _tokens_lock:
        return _read_tokens().get(platform)


def set_token(platform: str, data: dict | None) -> None:
    """Store (or with None, forget) an entry, such as "browser:instagram" once you've logged in to Instagram."""
    with _tokens_lock:
        tokens = _read_tokens()
        if data is None:
            tokens.pop(platform, None)
        else:
            tokens[platform] = data
        DATA_DIR.mkdir(exist_ok=True)
        tmp = TOKENS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens, indent=2), "utf-8")
        tmp.replace(TOKENS_PATH)
