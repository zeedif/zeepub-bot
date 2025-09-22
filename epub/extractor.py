import logging
import xml.etree.ElementTree as ET

from http.fetcher import fetch_bytes, cleanup_tmp
from telegram_utils.formatter import limpiar_html_basico
from config import OPDS_ROOT_EVIL


async def obtener_sinopsis_opds(series_id: str):
    if not series_id:
        return None
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        content = data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary_elem = root.find(".//atom:summary", ns)
        if summary_elem is not None and summary_elem.text:
            return " ".join(summary_elem.text.split())
    except Exception as e:
        logging.error("Error obteniendo sinopsis OPDS: %s", e)
    finally:
        cleanup_tmp(data)
    return None


async def obtener_sinopsis_opds_volumen(series_id: str, volume_id: str):
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        content = data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
                    summary_elem = entry.find("atom:summary", ns)
                    if summary_elem is not None and summary_elem.text:
                        texto = summary_elem.text.strip()
                        if "Summary:" in texto:
                            texto = texto.split("Summary:", 1)[1].strip()
                        return limpiar_html_basico(texto)
    except Exception as e:
        logging.error("Error obteniendo sinopsis volumen: %s", e)
    finally:
        cleanup_tmp(data)
    return None