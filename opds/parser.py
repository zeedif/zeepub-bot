import os
import io
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any

import feedparser

from http.fetcher import fetch_bytes, cleanup_tmp
from config import OPDS_ROOT_EVIL


async def parse_feed_from_url(url: str):
    """
    Descarga (usando fetch_bytes) y parsea un feed OPDS con feedparser.
    Maneja bytes o rutas a ficheros temporales.
    Devuelve feedparser.FeedParserDict o None en fallo.
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
        cleanup_tmp(data)


async def obtener_metadatos_opds(series_id: str, volume_id: str) -> Dict[str, Any]:
    """
    Extrae metadatos de una serie/volumen desde el feed OPDS "evil".
    """
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    datos = {
        "titulo_serie": None,
        "titulo_volumen": None,
        "autor": None,
        "ilustrador": None,
        "generos": [],
        "tags": [],
        "categoria": None,
        "demografia": None
    }

    data = await fetch_bytes(url, timeout=10)
    if not data:
        return datos

    try:
        content = data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read()
        root = ET.fromstring(content)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/terms/"
        }
        feed_title = root.find("atom:title", ns)
        if feed_title is not None and feed_title.text:
            datos["titulo_serie"] = feed_title.text.strip()
            datos["categoria"] = None

        for entry in root.findall("atom:entry", ns):
            # localizar el volumen correcto
            is_target = False
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
                    is_target = True
                    break
            if not is_target:
                continue

            vol_title = entry.find("atom:title", ns)
            if vol_title is not None and vol_title.text:
                datos["titulo_volumen"] = vol_title.text.strip()

            author_elem = entry.find("atom:author/atom:name", ns)
            if author_elem is not None and author_elem.text:
                datos["autor"] = author_elem.text.strip()

            for cat in entry.findall("atom:category", ns):
                term = cat.attrib.get("term", "").strip()
                scheme = cat.attrib.get("scheme", "").lower()
                if "genre" in scheme:
                    datos["generos"].append(term)
                elif "tag" in scheme:
                    datos["tags"].append(term)
                elif "demographic" in scheme:
                    datos["demografia"] = term
                elif "category" in scheme and not datos["categoria"]:
                    datos["categoria"] = term

            for creator in entry.findall("dc:creator", ns):
                role = creator.attrib.get("role", "").lower()
                if "illustrator" in role or "artist" in role:
                    datos["ilustrador"] = (creator.text or "").strip()

            # ya encontramos el volumen
            break
    except Exception as e:
        logging.error("Error obteniendo metadatos OPDS: %s", e)
    finally:
        cleanup_tmp(data)

    return datos