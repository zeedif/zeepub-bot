# services/metadata_service.py

import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any
from config.config_settings import config
from utils.http_client import fetch_bytes, cleanup_tmp
from utils.helpers import limpiar_html_basico

logger = logging.getLogger(__name__)


async def obtener_sinopsis_opds(series_id: str) -> Optional[str]:
    """Obtiene la sinopsis de una serie desde OPDS."""
    if not series_id:
        return None
    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        if isinstance(data, (bytes, bytearray)):
            content = data
        else:
            import aiofiles

            async with aiofiles.open(data, "rb") as f:
                content = await f.read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary = root.find(".//atom:summary", ns)
        if summary is not None and summary.text:
            return " ".join(summary.text.split())
    except Exception as e:
        logger.error(f"Error sinopsis OPDS serie {series_id}: {e}")
    finally:
        cleanup_tmp(data)
    return None


async def obtener_sinopsis_opds_volumen(
    series_id: str, volume_id: str
) -> Optional[str]:
    """Obtiene la sinopsis específica de un volumen."""
    if not series_id or not volume_id:
        return None
    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        if isinstance(data, (bytes, bytearray)):
            content = data
        else:
            import aiofiles

            async with aiofiles.open(data, "rb") as f:
                content = await f.read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            link = entry.find("atom:link", ns)
            href = link.attrib.get("href", "")
            if f"/volume/{volume_id}/" in href:
                summary = entry.find("atom:summary", ns)
                if summary is not None and summary.text:
                    return limpiar_html_basico(summary.text)
    except Exception as e:
        logger.error(f"Error sinopsis OPDS volumen {volume_id}: {e}")
    finally:
        cleanup_tmp(data)
    return None


async def obtener_metadatos_opds(series_id: str, volume_id: str) -> Dict[str, Any]:
    """Extrae metadatos (título, autor, géneros, etc.) desde OPDS."""
    datos: Dict[str, Any] = {
        "titulo_serie": None,
        "titulo_volumen": None,
        "autor": None,
        "ilustrador": None,
        "generos": [],
        "tags": [],
        "categoria": None,
        "demografia": None,
        "fecha_publicacion": None,
    }
    if not series_id or not volume_id:
        return datos

    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return datos
    try:
        if isinstance(data, (bytes, bytearray)):
            content = data
        else:
            import aiofiles

            async with aiofiles.open(data, "rb") as f:
                content = await f.read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/terms/"}

        # Título de la serie
        feed_title = root.find("atom:title", ns)
        if feed_title is not None and feed_title.text:
            datos["titulo_serie"] = feed_title.text.strip()

        # Entrada del volumen
        for entry in root.findall("atom:entry", ns):
            hrefs = [
                link.attrib.get("href", "") for link in entry.findall("atom:link", ns)
            ]
            if any(f"/volume/{volume_id}/" in href for href in hrefs):
                # Título volumen
                title_el = entry.find("atom:title", ns)
                if title_el is not None and title_el.text:
                    datos["titulo_volumen"] = title_el.text.strip()

                # Autor
                author_el = entry.find("atom:author/atom:name", ns)
                if author_el is not None and author_el.text:
                    datos["autor"] = author_el.text.strip()

                # Categorías y géneros
                for cat in entry.findall("atom:category", ns):
                    term = cat.attrib.get("term", "").strip()
                    scheme = cat.attrib.get("scheme", "").lower()
                    if "genre" in scheme:
                        datos["generos"].append(term)
                    elif "demographic" in scheme:
                        datos["demografia"] = term
                    else:
                        datos["categoria"] = term

                # Ilustrador y tags
                for creator in entry.findall("dc:creator", ns):
                    role = creator.attrib.get("role", "").lower()
                    if "illustrator" in role or "artist" in role:
                        datos["ilustrador"] = creator.text.strip()

                # Fecha publicación (dc:date o dcterms:issued)
                # Intentamos con el namespace definido (dc -> terms)
                date_el = entry.find("dc:date", ns)
                if date_el is not None and date_el.text:
                    datos["fecha_publicacion"] = date_el.text.strip()
                else:
                    # Si no, probamos con dcterms:issued si existiera (aunque ns dc es terms)
                    issued = entry.find("dc:issued", ns)
                    if issued is not None and issued.text:
                        datos["fecha_publicacion"] = issued.text.strip()
                break

    except Exception as e:
        logger.error(f"Error metadatos OPDS serie_vol {series_id}/{volume_id}: {e}")
    finally:
        cleanup_tmp(data)
    return datos
