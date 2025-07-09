import itertools, asyncio, os
from typing import List, Optional

class ProxyPool:
    def __init__(self, proxies: List[str]):
        self._proxies   = proxies or [None]
        self._cycle     = itertools.cycle(self._proxies)
        self._lock      = asyncio.Lock()

    async def next(self) -> Optional[str]:
        async with self._lock:
            return next(self._cycle)

    async def ban(self, proxy: str):
        if proxy in self._proxies:
            self._proxies.remove(proxy)
            self._cycle = itertools.cycle(self._proxies or [None])

PROXY_POOL = [p for p in os.getenv("PROXY_POOL", "").split(",") if p]

def pool_from_env(raw: List[str]):
    return ProxyPool(raw or PROXY_POOL)

