from fastapi import APIRouter, HTTPException, Query, Request, Response
from typing import Optional, Dict, Any
import aiohttp
from config.config_settings import config
from utils.http_client import parse_feed_from_url
from utils.helpers import build_search_url
import logging

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.get("/feed")
async def get_feed(url: Optional[str] = None, uid: Optional[int] = None):
    """
    Obtiene el feed OPDS. Si no se proporciona URL, usa el root por defecto.
    Verifica permisos si se proporciona uid.
    """
    logger.info(f"Feed request - UID: {uid}, URL: {url}")
    
    # Verificar permisos si hay UID
    if uid:
        allowed = (
            uid in config.WHITELIST or 
            uid in config.VIP_LIST or 
            uid in config.PREMIUM_LIST or
            uid in config.ADMIN_USERS
        )
        if not allowed:
            raise HTTPException(
                status_code=403, 
                detail="⛔ Esta función solo está disponible para usuarios VIP, Premium o Patrocinadores por el momento."
            )

    target_url = url if url else config.OPDS_ROOT_START
    try:
        feed = await parse_feed_from_url(target_url)
        if not feed:
            raise HTTPException(status_code=404, detail="No se pudo cargar el feed")
        
        # Helper para normalizar URLs
        def normalize_url(href):
            if not href:
                return None
            # Si es una URL absoluta, devolverla tal cual
            if href.startswith('http://') or href.startswith('https://'):
                return href
            # Si es relativa, construir URL absoluta
            base = config.BASE_URL.rstrip('/')
            if href.startswith('/'):
                return f"{base}{href}"
            return f"{base}/{href}"
        
        # Convertir feedparser object a dict serializable
        entries = []
        for entry in getattr(feed, "entries", []):
            # Extraer imagen - buscar en múltiples lugares
            cover_url = None
            
            # Primero buscar en links
            for link in getattr(entry, "links", []):
                link_type = link.get("type", "")
                link_rel = link.get("rel", "")
                if "image" in link_type or "cover" in link_rel or link_rel == "http://opds-spec.org/image":
                    cover_url = normalize_url(link.get("href"))
                    break
            
            # Si no encontramos, buscar en content
            if not cover_url and hasattr(entry, 'content'):
                for content in entry.content:
                    if 'image' in content.get('type', ''):
                        cover_url = normalize_url(content.get('value'))
                        break
            
            entries.append({
                "title": entry.get("title", "Sin título"),
                "author": entry.get("author", "Desconocido"),
                "summary": entry.get("summary", ""),
                "id": entry.get("id", ""),
                "cover_url": cover_url,
                "links": [
                    {"href": normalize_url(l.get("href")), "rel": l.get("rel"), "type": l.get("type")}
                    for l in getattr(entry, "links", [])
                ]
            })

        def normalize_url(href):
            if not href: return None
            if href.startswith('http'):
                return href
            
            # Fallback si BASE_URL no está configurado
            base = (config.BASE_URL or "https://zeepubs.com").rstrip('/')
            
            if href.startswith('/'):
                return f"{base}{href}"
            return f"{base}/{href}"

        processed_links = [
            {"href": normalize_url(l.get("href")), "rel": l.get("rel"), "type": l.get("type")}
            for l in getattr(feed.feed, "links", [])
        ]

        return {
            "title": getattr(feed.feed, "title", "ZeePub Feed"),
            "links": processed_links,
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

@router.get("/image/{rest_of_path:path}")
async def proxy_image(rest_of_path: str, request: Request):
    """
    Proxies image requests to the upstream OPDS server.
    """
    try:
        # Reconstruct the full URL
        # The original BASE_URL might be the root of the OPDS server,
        # so we append the rest_of_path directly.
        # Ensure BASE_URL does not end with a slash if rest_of_path doesn't start with one.
        base_url_cleaned = config.BASE_URL.rstrip('/')
        full_url = f"{base_url_cleaned}/{rest_of_path}"
        
        # Get query parameters from the original request
        query_params = dict(request.query_params)
        
        # Make request to upstream server using httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(full_url, params=query_params, follow_redirects=True)
            
            # If the upstream server returns an error, raise an HTTPException
            response.raise_for_status() 
            
            # Return the image with appropriate headers
            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                }
            )
    except httpx.HTTPStatusError as e:
        logger.error(f"Error proxying image {full_url}: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="Image not found upstream or error fetching")
    except httpx.RequestError as e:
        logger.error(f"Network error proxying image {full_url}: {e}")
        raise HTTPException(status_code=500, detail="Network error fetching image")
    except Exception as e:
        logger.error(f"Unexpected error proxying image {full_url}: {e}")
        raise HTTPException(status_code=500, detail="Error proxying image")

@router.post("/download")
async def download_book(request: Request):
    """
    Handle EPUB download requests from Mini App.
    Uses enviar_libro_directo to match bot format.
    """
    try:
        data = await request.json()
        title = data.get('title', 'Libro')
        download_url = data.get('download_url')
        cover_url = data.get('cover_url')
        user_id = data.get('user_id')
        
        if not download_url or not user_id:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        logger.info(f"Download request from user {user_id}: {title}")
        
        # Get bot from main.py
        from api.main import bot
        from services.telegram_service import enviar_libro_directo
        
        # Run the download process in background to avoid blocking API? 
        # For now, await it to report success/failure.
        success = await enviar_libro_directo(
            bot.app.bot,
            user_id=user_id,
            title=title,
            download_url=download_url,
            cover_url=cover_url
        )
        
        if success:
            return {"status": "success", "message": "Download completed"}
        else:
            raise HTTPException(status_code=500, detail="Download failed")
            
    except Exception as e:
        logger.error(f"Error in download endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
