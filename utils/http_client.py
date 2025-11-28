# utils/http_client.py

import os
import asyncio
import aiohttp
import feedparser
import tempfile
from typing import Union
from core.session_manager import session_manager
import logging

logger = logging.getLogger(__name__)

MAX_IN_MEMORY_BYTES = 10 * 1024 * 1024  # 10MB


def cleanup_tmp(path):
    """Elimina archivo temporal si existe."""
    if isinstance(path, str) and os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


async def fetch_bytes(
    url: str, session: aiohttp.ClientSession = None, timeout: int = 15
) -> Union[bytes, str, None]:
    """
    Descarga el contenido de `url`. Si supera MAX_IN_MEMORY_BYTES escribe a fichero temporal.
    Retorna bytes o ruta al fichero temporal, o None en error.
    """
    try:
        sess = session or session_manager.get_session()
        logger.debug("Iniciando descarga de URL OPDS: %s", url)
        async with sess.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            cl = resp.headers.get("Content-Length")
            total = None
            if cl:
                try:
                    total = int(cl)
                except ValueError:
                    total = None
            # Si sabemos el tamaño y es grande, stream a archivo
            if total is not None and total > MAX_IN_MEMORY_BYTES:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        # Offload blocking disk writes to threadpool
                        await asyncio.to_thread(tmp.write, chunk)
                    tmp.close()
                    logger.debug(
                        "fetch_bytes devolvió archivo temporal: %s (%d bytes)",
                        tmp.name,
                        total,
                    )
                    return tmp.name
                except Exception as e:
                    logger.error(
                        "Error al escribir chunks en tmpfile %s: %s", tmp.name, e
                    )
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
            # Si es pequeño (o tamaño desconocido), leer todo en memoria
            data = await resp.read()
            length = len(data)
            if length > MAX_IN_MEMORY_BYTES:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    # Write the whole payload to disk via threadpool to avoid blocking
                    await asyncio.to_thread(tmp.write, data)
                    tmp.close()
                    logger.debug(
                        "fetch_bytes devolvió archivo temporal por tamaño real: %s (%d bytes)",
                        tmp.name,
                        length,
                    )
                    return tmp.name
                except Exception as e:
                    logger.error(
                        "Error al escribir data en tmpfile %s: %s", tmp.name, e
                    )
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
            logger.debug("fetch_bytes devolvió bytes en memoria (%d bytes)", length)
            return data
    except Exception as e:
        logger.error("Error fetch_bytes %s: %s", url, e)
        return None


async def parse_feed_from_url(url: str):
    """
    Descarga y parsea un feed OPDS con feedparser.
    Retorna objeto feedparser.FeedParserDict o None en error.
    """
    data = await fetch_bytes(url, timeout=20)
    if not data:
        logger.error("parse_feed_from_url: fetch_bytes devolvió None para %s", url)
        return None
    try:
        if isinstance(data, (bytes, bytearray)):
            feed = await asyncio.to_thread(feedparser.parse, data)
        elif isinstance(data, str) and os.path.exists(data):
            try:
                with open(data, "rb") as f:
                    content = f.read()
            except Exception as e:
                logger.error(
                    "parse_feed_from_url: error leyendo tmpfile %s: %s", data, e
                )
                return None
            feed = await asyncio.to_thread(feedparser.parse, content)
        else:
            feed = await asyncio.to_thread(feedparser.parse, data)
        if getattr(feed, "bozo", False):
            logger.error("parse_feed_from_url: bozo flag true para %s", url)
            return None
        return feed
    finally:
        cleanup_tmp(data)
