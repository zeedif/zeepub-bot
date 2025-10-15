import os
import tempfile
import asyncio
import httpx
import feedparser
import logging
from config.config_settings import config

logger = logging.getLogger(__name__)

# Cliente httpx global con keep-alive y pool persistente
HTTP_CLIENT = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10, read=180, write=180, pool=30)
)

async def fetch_bytes(url: str, timeout: int = 60):
    """
    Descarga y retorna:
     - bytes si contenido pequeño (<= MAX_IN_MEMORY_BYTES)
     - path de archivo temporal (str) si es grande
    Devuelve None en error.
    """
    try:
        resp = await HTTP_CLIENT.get(url, timeout=timeout)
        resp.raise_for_status()
        cl = resp.headers.get("Content-Length")
        total = int(cl) if cl and cl.isdigit() else None

        if total is not None and total > config.MAX_IN_MEMORY_BYTES:
            tmp = tempfile.NamedTemporaryFile(delete=False)
            try:
                for chunk in resp.iter_bytes(64 * 1024):
                    tmp.write(chunk)
                tmp.close()
                return tmp.name
            except Exception as e:
                logger.warning(f"Error guardando archivo grande: {e}")
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                return None
        else:
            data = resp.content
            if len(data) > config.MAX_IN_MEMORY_BYTES:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    tmp.write(data)
                    tmp.close()
                    return tmp.name
                except Exception:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
            return data
    except Exception as e:
        logger.warning(f"Error fetch_bytes {url}: {e}")
        return None

async def parse_feed_from_url(url: str):
    """
    Descarga (fetch_bytes) y parsea OPDS con feedparser.
    """
    data = await fetch_bytes(url, timeout=20)
    if not data:
        return None

    try:
        if isinstance(data, (bytes, bytearray)):
            feed = await asyncio.to_thread(feedparser.parse, data)
        elif isinstance(data, str) and os.path.exists(data):
            try:
                with open(data, "rb") as f:
                    content = f.read()
            except Exception:
                return None
            feed = await asyncio.to_thread(feedparser.parse, content)
        else:
            feed = await asyncio.to_thread(feedparser.parse, data)
        return None if getattr(feed, "bozo", False) else feed
    finally:
        # Limpieza segura de tempfiles
        from utils.decorators import cleanup_tmp
        cleanup_tmp(data)

class AsyncLRUCache:
    def __init__(self, maxsize=64):
        self.cache = dict()
        self.queue = []
        self.maxsize = maxsize
        self.lock = asyncio.Lock()

    async def get(self, key, getter):
        async with self.lock:
            if key in self.cache:
                self.queue.remove(key)
                self.queue.append(key)
                return self.cache[key]

            value = await getter()
            self.cache[key] = value
            self.queue.append(key)

            if len(self.queue) > self.maxsize:
                remove_key = self.queue.pop(0)
                del self.cache[remove_key]

            return value

async_cache = AsyncLRUCache(maxsize=128)

async def fetch_bytes_cached(url: str):
    async def getter():
        return await fetch_bytes(url)
    return await async_cache.get(url, getter)
