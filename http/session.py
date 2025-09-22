import aiohttp
from config import DEFAULT_AIOHTTP_TIMEOUT

_GLOBAL_AIOSESSION = None

def get_global_session(create_if_missing: bool = True) -> aiohttp.ClientSession | None:
    global _GLOBAL_AIOSESSION
    if _GLOBAL_AIOSESSION is None and create_if_missing:
        connector = aiohttp.TCPConnector(limit=20)
        _GLOBAL_AIOSESSION = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_AIOHTTP_TIMEOUT)
        )
    return _GLOBAL_AIOSESSION