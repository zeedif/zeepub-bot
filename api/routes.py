from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from config.config_settings import config
from utils.http_client import parse_feed_from_url
from utils.helpers import build_search_url
import logging

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.get("/feed")
async def get_feed(url: Optional[str] = None):
    """
    Obtiene el feed OPDS. Si no se proporciona URL, usa el root por defecto.
    """
    target_url = url if url else config.OPDS_ROOT_START
    try:
        feed = await parse_feed_from_url(target_url)
        if not feed:
            raise HTTPException(status_code=404, detail="No se pudo cargar el feed")
        
        # Convertir feedparser object a dict serializable
        entries = []
        for entry in getattr(feed, "entries", []):
            # Extraer imagen
            cover_url = None
            for link in getattr(entry, "links", []):
                if "image" in link.get("type", "") or "cover" in link.get("rel", ""):
                    cover_url = link.get("href")
                    break
            
            entries.append({
                "title": entry.get("title", "Sin título"),
                "author": entry.get("author", "Desconocido"),
                "summary": entry.get("summary", ""),
                "id": entry.get("id", ""),
                "cover_url": cover_url,
                "links": [
                    {"href": l.get("href"), "rel": l.get("rel"), "type": l.get("type")}
                    for l in getattr(entry, "links", [])
                ]
            })

        return {
            "title": getattr(feed.feed, "title", "ZeePub Feed"),
            "entries": entries
        }
    except Exception as e:
        logger.error(f"Error fetching feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
async def search_books(q: str = Query(..., min_length=1)):
    """
    Busca libros usando el término proporcionado.
    """
    # Usamos un ID ficticio (0) para la búsqueda pública de la API
    search_url = build_search_url(q, uid=0)
    return await get_feed(url=search_url)
