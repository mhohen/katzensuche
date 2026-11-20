"""Lightweight stdlib HTTP helper with retries and clean error classification."""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.5",
    "Accept-Encoding": "gzip",
}


class FetchBlockedError(RuntimeError):
    """Raised when a remote site returns 403/429 or an anti-bot challenge page."""


def fetch_text(url: str, timeout_sec: int = 20, retries: int = 2) -> str:
    """Fetch URL content as UTF-8 text using Python stdlib only."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", errors="ignore")
                # Detect common anti-bot / challenge walls explicitly (never attempt to bypass)
                lower_head = text[:4000].lower()
                if (
                    "just a moment..." in lower_head
                    and ("cf-browser-verification" in lower_head or "challenge-platform" in lower_head)
                ):
                    raise FetchBlockedError(f"Anti-Bot-Challenge erkannt auf {url}")
                return text
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):
                last_err = FetchBlockedError(f"HTTP {e.code} auf {url}")
            else:
                last_err = RuntimeError(f"HTTP {e.code} auf {url}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = RuntimeError(f"Netzwerkfehler auf {url}: {e}")

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    assert last_err is not None
    raise last_err
