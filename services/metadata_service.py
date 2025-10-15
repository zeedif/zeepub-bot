# services/metadata_service.py
import logging
import xml.etree.ElementTree as ET
from config.config_settings import config
from utils.http_client import fetch_bytes
from utils.helpers import limpiar_html_basico
from utils.decorators import cleanup_tmp

logger = logging.getLogger(__name__)

async def obtener_sinopsis_opds(series_id: str):
    """Get synopsis from OPDS series feed"""
    if not series_id:
        return None
    
    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    
    try:
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary_elem = root.find(".//atom:summary", ns)
        if summary_elem is not None and summary_elem.text:
            return " ".join(summary_elem.text.split())
    except Exception as e:
        logger.error(f"Error obteniendo sinopsis OPDS: {e}")
    finally:
        cleanup_tmp(data)
    return None

async def obtener_sinopsis_opds_volumen(series_id: str, volume_id: str):
    """Get synopsis for specific volume from OPDS"""
    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    
    try:
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
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
        logger.error(f"Error obteniendo sinopsis volumen: {e}")
    finally:
        cleanup_tmp(data)
    return None

async def obtener_metadatos_opds(series_id: str, volume_id: str):
    """Get metadata from OPDS feed"""
    url = f"{config.OPDS_ROOT_EVIL}/series/{series_id}"
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
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/terms/"
        }
        
        feed_title = root.find("atom:title", ns)
        if feed_title is not None and feed_title.text:
            titulo_serie = feed_title.text.strip()
            datos["titulo_serie"] = titulo_serie
            datos["categoria"] = None  # Category should come from OPF or explicit OPDS categories
        
        for entry in root.findall("atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
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
                            datos["ilustrador"] = creator.text.strip()
                    break
    except Exception as e:
        logger.error(f"Error obteniendo metadatos OPDS: {e}")
    finally:
        cleanup_tmp(data)
    
    return datos