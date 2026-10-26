"""Paths, config.toml and the local login store (which platforms you've logged in to in ReelForge's browser).

Each profile (each channel, see studio/profiles.py) has its own settings and data: HOME is the profile's dashboard
folder, with its config.toml (CONFIG_PATH) and data/ (DATA_DIR: DB_PATH, the stats, and TOKENS_PATH, its log-ins).
They're the profile's this process works on, looked up each time; the first profile's are this folder's own, as
they always were."""

from __future__ import annotations

import json
import shutil
import threading
import tomllib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent     # the dashboard's code, and the first profile's settings, data/, videos/

PLATFORM_KEYS = ("tiktok", "youtube", "instagram", "x")

_tokens_lock = threading.Lock()


def profile():
    """The profile this process works on (studio/profiles.py), or None for a dashboard run outside a ReelForge
    folder."""
    try:
        from studio import profiles
    except ImportError:
        return None
    return profiles.current()


def _set(name: str) -> Path | None:
    """A path set on this module by hand (the tests point them at scratch folders)."""
    return globals().get(name)


def home() -> Path:
    """The profile's dashboard folder: its config.toml and data/, and where relative paths in config.toml start."""
    if _set("HOME"):
        return _set("HOME")
    p = profile()
    return APP_DIR if p is None or p.main else p.dashboard


def config_path() -> Path:
    return _set("CONFIG_PATH") or home() / "config.toml"


def data_dir() -> Path:
    return _set("DATA_DIR") or home() / "data"


def db_path() -> Path:
    return _set("DB_PATH") or data_dir() / "stats.db"


def tokens_path() -> Path:
    return _set("TOKENS_PATH") or data_dir() / "tokens.json"


_PATHS = {"HOME": home, "CONFIG_PATH": config_path, "DATA_DIR": data_dir, "DB_PATH": db_path,
          "TOKENS_PATH": tokens_path}


def __getattr__(name: str):
    if name in _PATHS:
        return _PATHS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ConfigError(Exception):
    """config.toml can't be read; the message says where."""


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(APP_DIR / "config.example.toml", path)
    try:
        with path.open("rb") as f:
            cfg = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name} has a typo ({e}). Fix it in a text editor, or delete the file "
                          "and ReelForge makes a fresh one from config.example.toml.") from e
    for key in PLATFORM_KEYS:
        if not isinstance(cfg.get(key), dict):
            cfg[key] = {}
    return cfg


def save_handle(platform: str, handle: str) -> None:
    """Connect a platform ("@name") or disconnect it (""): its handle in config.toml, the rest of the file as it was.
    Your studio's settings follow (studio.generate.set_account), so your AI's notes cover the platforms you're
    connected to and running onboarding again keeps them."""
    load_config()  # config.toml from the example, if there isn't one yet
    from studio import dashboard_config, generate

    path = config_path()
    if path.resolve() == dashboard_config.config_toml().resolve():  # this profile's own
        generate.set_account(platform, handle)
    else:  # a config.toml somewhere else (the tests): only its handle
        dashboard_config.set_handle(platform, handle, path)


def resolve(path: str) -> Path:
    """Resolve a config path relative to the profile's dashboard folder (for the first profile, this folder)."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (home() / p).resolve()


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
    path = tokens_path()
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
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
        path = tokens_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens, indent=2), "utf-8")
        tmp.replace(path)
