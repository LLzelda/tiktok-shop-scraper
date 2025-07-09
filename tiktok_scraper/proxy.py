import itertools, random, asyncio
from typing import Optional, List
import os
class ProxyPool:
    def __init__(self, proxies: List[str]):
        self._proxies = proxies or [None]
        self._cycle = itertools.cycle(self._proxies)
        self._lock = asyncio.Lock()

    async def next(self) -> Optional[str]:
        async with self._lock:
            return next(self._cycle)
        
    # async def ban(self, proxy):
    #     self._proxies.remove(proxy)
    #     self._cycle = itertools.cycle(self._proxies or [None])
        
#PROXY_POOL = [p for p in os.getenv("PROXY_POOL", "").split(",") if p]

def pool_from_env(env_list):
    return ProxyPool(env_list)
