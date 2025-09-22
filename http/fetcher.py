import os
import tempfile
import logging
import aiohttp

from config import MAX_IN_MEMORY_BYTES
from http.session import get_global_session


def cleanup_tmp(path: str):
    if isinstance(path, str) and os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


async def fetch_bytes(url: str, session: aiohttp.ClientSession = None, timeout: int = 15):
    """
    Devuelve:
      - bytes cuando el contenido es pequeño <= MAX_IN_MEMORY_BYTES
      - ruta a fichero temporal (str) cuando es grande
    None en fallo.
    """
    try:
        sess = session or get_global_session()
        async with sess.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            cl = resp.headers.get("Content-Length")
            total = None
            if cl:
                try:
                    total = int(cl)
                except Exception:
                    total = None

            if total is not None and total > MAX_IN_MEMORY_BYTES:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        tmp.write(chunk)
                    tmp.close()
                    return tmp.name
                except Exception:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
            else:
                data = await resp.read()
                if len(data) > MAX_IN_MEMORY_BYTES:
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
        logging.debug("Error fetch_bytes %s: %s", url, e)
        return None