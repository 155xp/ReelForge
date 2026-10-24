"""Downloads that work on fresh Windows installs too.

Python's own certificate check fails on some Windows PCs ("certificate has expired") for sites whose root
certificate Windows only fetches on demand. truststore asks the operating system to check certificates the way
browsers do; certifi's bundle is the fallback.
"""

from __future__ import annotations

import ssl
import urllib.request

_CTX: ssl.SSLContext | None = None
AGENT = "reelforge-setup"


def ssl_context() -> ssl.SSLContext:
    global _CTX
    if _CTX is None:
        try:
            import truststore

            _CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            try:
                import certifi

                _CTX = ssl.create_default_context(cafile=certifi.where())
                _CTX.load_default_certs()
            except Exception:
                _CTX = ssl.create_default_context()
    return _CTX


def open_url(url: str, timeout: float = 60):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def fetch_text(url: str) -> str:
    with open_url(url) as r:
        return r.read().decode("utf-8", "replace")


def fetch_bytes(url: str) -> bytes:
    with open_url(url) as r:
        return r.read()
