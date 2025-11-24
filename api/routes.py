
from fastapi import APIRouter, HTTPException, Query, Request, Response, Depends, Header
from typing import Optional, Dict, Any
import aiohttp
import httpx
from config.config_settings import config
from utils.http_client import parse_feed_from_url
from utils.helpers import build_search_url
from utils.security import validate_telegram_data
import logging

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

async def get_current_user(
    x_telegram_data: Optional[str] = Header(None, alias="X-Telegram-Data"),
    uid: Optional[int] = Query(None)
) -> int:
    """
    Valida el usuario mediante initData (si está disponible) o confía en uid (legacy/dev).
    En producción, se debería forzar el uso de initData.
    """
    # Si hay initData, validarlo
    if x_telegram_data:
        user_data = validate_telegram_data(x_telegram_data, config.TELEGRAM_TOKEN)
        if not user_data:
            logger.warning(f"Invalid initData received: {x_telegram_data[:20]}...")
            raise HTTPException(status_code=401, detail="Invalid Telegram data")
        
        # Extraer ID del usuario validado
        validated_uid = user_data.get("user", {}).get("id")
        if not validated_uid:
            raise HTTPException(status_code=401, detail="User ID not found in data")
            
        return validated_uid

    # Fallback para desarrollo o si no se envía header (opcional, se puede quitar para mayor seguridad)
    # Por ahora permitimos uid directo si no hay header, pero logueamos advertencia
    if uid:
        # logger.warning(f"Insecure access with raw UID: {uid}")
        return uid
        
    # Si no hay ni header ni uid, permitimos acceso anónimo (para feed público)
    return 0

@router.get("/feed")
async def get_feed(
    url: Optional[str] = None, 
    current_uid: int = Depends(get_current_user)
):
    """
    Obtiene el feed OPDS.
    """
    logger.info(f"Feed request - UID: {current_uid}, URL: {url}")
    
    # Verificar permisos si hay UID (y no es anónimo)
    if current_uid > 0:
        allowed = (
            current_uid in config.WHITELIST or 
            current_uid in config.VIP_LIST or 
            current_uid in config.PREMIUM_LIST or
            current_uid in config.ADMIN_USERS
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
            if not href: return None
            if href.startswith('http'): return href
            
            base = (config.BASE_URL or "https://zeepubs.com").rstrip('/')
            if href.startswith('/'): return f"{base}{href}"
            return f"{base}/{href}"
        
        # Convertir feedparser object a dict serializable
        entries = []
        for entry in getattr(feed, "entries", []):
            cover_url = None
            # Buscar cover en links
            for link in getattr(entry, "links", []):
                link_type = link.get("type", "")
                link_rel = link.get("rel", "")
                if "image" in link_type or "cover" in link_rel or link_rel == "http://opds-spec.org/image":
                    cover_url = normalize_url(link.get("href"))
                    break
            
            # Buscar cover en content
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
async def search_books(
    q: str = Query(..., min_length=1),
    current_uid: int = Depends(get_current_user)
):
    """
    Busca libros usando el término proporcionado.
    """
    # Usamos el UID validado para construir la URL de búsqueda (si es necesario)
    search_url = build_search_url(q, uid=current_uid)
    return await get_feed(url=search_url, current_uid=current_uid)

@router.get("/image/{rest_of_path:path}")
async def proxy_image(rest_of_path: str, request: Request):
    """
    Proxies image requests to the upstream OPDS server.
    """
    try:
        base_url_cleaned = config.BASE_URL.rstrip('/')
        full_url = f"{base_url_cleaned}/{rest_of_path}"
        query_params = dict(request.query_params)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(full_url, params=query_params, follow_redirects=True)
            response.raise_for_status() 
            
            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=86400"}
            )
    except Exception as e:
        logger.error(f"Error proxying image: {e}")
        raise HTTPException(status_code=404, detail="Image not found")

@router.post("/download")
async def download_book(
    request: Request,
    current_uid: int = Depends(get_current_user)
):
    """
    Handle EPUB download requests from Mini App.
    """
    try:
        data = await request.json()
        title = data.get('title', 'Libro')
        download_url = data.get('download_url')
        cover_url = data.get('cover_url')
        
        # Validar que el usuario autenticado coincida con el solicitado (o simplemente usar el autenticado)
        # Aquí forzamos el uso del usuario autenticado para mayor seguridad
        user_id = current_uid
        
        if not download_url or not user_id:
            raise HTTPException(status_code=400, detail="Missing required fields or authentication")
        
        logger.info(f"Download request from user {user_id}: {title}")
        
        from api.main import bot
        from services.telegram_service import enviar_libro_directo
        
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
