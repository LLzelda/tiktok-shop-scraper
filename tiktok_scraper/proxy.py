import itertools
import asyncio
import os
from typing import List, Optional


class ProxyPool:
    """round-robin helper with a simple ban circuit-breaker.

    • Keeps an in-memory list of proxies (strings of the form
      `user:pass@host:port` or just `host:port`).
    • `None` in the list means *direct-to-internet* (no proxy).
    • Thread-safe for asyncio coroutines via an internal lock.
    """

    def __init__(self, proxies: List[Optional[str]]):
        # ‑‑ deduplicate while preserving order
        seen: set[str | None] = set()
        self._proxies: List[Optional[str]] = [
            p for p in proxies if p and p not in seen and not seen.add(p)
        ]
        if not self._proxies:
            self._proxies = [None]  # fall back to direct connection

        self._cycle = itertools.cycle(self._proxies)
        self._lock = asyncio.Lock()

    async def next(self) -> Optional[str]:
        """Return the next proxy (or None for direct)."""
        async with self._lock:
            return next(self._cycle)

    async def ban(self, proxy: Optional[str]) -> None:
        """Remove a misbehaving proxy, e.g. when we hit CAPTCHA/403."""
        async with self._lock:
            if proxy in self._proxies:
                self._proxies.remove(proxy)
                if not self._proxies:
                    self._proxies = [None]
                self._cycle = itertools.cycle(self._proxies)


# ──────────────────────────────────────────────────────────────────────────────
# Global helper
# ──────────────────────────────────────────────────────────────────────────────

# Read once at import time so that "from tiktok_scraper.proxy import PROXY_POOL"
# works everywhere without recomputing.
PROXY_POOL: List[str] = [p for p in os.getenv("PROXY_POOL", "").split(",") if p]


def pool_from_env(raw: Optional[List[str]] = None) -> ProxyPool:
    """Return a :class:ProxyPool built from the given raw list or PROXY_POOL.

    Scraper code can call :pyfunc:pool_from_env() without arguments when it
    just wants “whatever is configured via the environment”.
    """
    raw = raw if raw is not None else PROXY_POOL
    return ProxyPool(raw)

