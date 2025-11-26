
from fastapi import APIRouter, HTTPException, Query, Request, Response, Depends, Header
from typing import Optional, Dict, Any
import aiohttp
import httpx
import os
from config.config_settings import config
from utils.http_client import parse_feed_from_url
from utils.helpers import build_search_url
from utils.security import validate_telegram_data
from utils.http_client import fetch_bytes
from services.epub_service import parse_opf_from_epub, extract_cover_from_epub
from utils.helpers import generar_slug_from_meta, formatear_mensaje_portada, formatear_titulo_fb
import logging
import re

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

from utils.url_cache import get_url_from_hash

@router.get("/dl/{url_hash}")
async def short_download(url_hash: str):
    """
    Endpoint acortado para descargas usando hash SHA256.
    """
    try:
        # Buscar en BD SQLite
        url = get_url_from_hash(url_hash)
        if not url:
            raise HTTPException(status_code=404, detail="Short URL not found")
        
        # Extraer título del final de la URL
        from urllib.parse import unquote, urlparse
        parsed = urlparse(url)
        title = unquote(parsed.path.split('/')[-1]).replace('.epub', '')
        
        # Redirigir al endpoint público
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/api/public/dl?url={url}&title={title}")
    except Exception as e:
        logger.error(f"Error decoding short URL: {e}")
        raise HTTPException(status_code=404, detail="Invalid short URL")

@router.get("/public/dl")
async def public_download(
    url: str = Query(..., description="Source EPUB URL"),
    title: str = Query("libro", description="Filename hint")
):
    """
    Proxy público para descargas.
    Sirve el archivo desde la fuente OPDS original.
    """
    try:
        # Validar URL básica para evitar SSRF flagrante (aunque fetch_bytes ya es genérico)
        if not url.startswith("http"):
            raise HTTPException(status_code=400, detail="Invalid URL")

        # Usar fetch_bytes para obtener el contenido (memoria o archivo temp)
        # Nota: fetch_bytes maneja archivos grandes escribiendo a disco
        data = await fetch_bytes(url, timeout=120)
        
        if not data:
            raise HTTPException(status_code=404, detail="Could not fetch file")

        from fastapi.responses import StreamingResponse

        # Determinar si es archivo o bytes
        if isinstance(data, str) and os.path.exists(data):
            # Es un archivo temporal
            def iterfile():
                try:
                    with open(data, mode="rb") as file_like:
                        yield from file_like
                finally:
                    # Intentar borrar después
                    try:
                        os.unlink(data)
                    except Exception as e:
                        logger.debug("Could not remove temp file from streaming proxy: %s", e)

            return StreamingResponse(
                content=iterfile(),
                media_type="application/epub+zip",
                headers={"Content-Disposition": f'attachment; filename="{title}.epub"'}
            )
        else:
            # Son bytes en memoria
            # StreamingResponse espera un iterador o bytes-like object?
            # Response normal funciona para bytes.
            return Response(
                content=data,
                media_type="application/epub+zip",
                headers={"Content-Disposition": f'attachment; filename="{title}.epub"'}
            )

    except Exception as e:
        logger.error(f"Error in public download proxy: {e}")
        raise HTTPException(status_code=500, detail="Download failed")

@router.post("/facebook/prepare")
async def prepare_facebook_post(
    request: Request,
    current_uid: int = Depends(get_current_user)
):
    """
    Prepara el texto y link para un post de Facebook.
    """
    if current_uid not in config.FACEBOOK_PUBLISHERS:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    try:
        data = await request.json()
        book = data.get('book')
        if not book:
            raise HTTPException(status_code=400, detail="Missing book data")
            
        # Extraer datos
        title = book.get('title', 'Libro')
        download_url = next((l['href'] for l in book.get('links', []) if 'acquisition' in l.get('rel', '') or 'epub' in l.get('type', '')), None)
        cover_url = book.get('cover_url')
        
        if not download_url:
            raise HTTPException(status_code=400, detail="No download URL found")

        # Construir link público acortado con SHA256
        from utils.url_cache import create_short_url
        from urllib.parse import quote, unquote, urlparse
        
        dl_domain = config.DL_DOMAIN.rstrip('/')
        # Asegurar esquema
        if not dl_domain.startswith("http"):
            dl_domain = f"https://{dl_domain}"
        
        # Crear hash y guardar en BD SQLite
        url_hash = create_short_url(download_url)
        public_link = f"{dl_domain}/api/dl/{url_hash}"
        
        # Intentar obtener metadatos completos del EPUB para el título
        header_title = f"📚 <b>{title}</b>" # Fallback
        
        try:
            # Descargar primeros bytes o todo para parsear
            epub_bytes = await fetch_bytes(download_url, timeout=60)
            if epub_bytes:
                meta = {"titulo": title, "epub_version": "2.0", "fecha_modificacion": "Desconocida"}
                
                # Parsear OPF
                opf_meta = await parse_opf_from_epub(epub_bytes)
                if opf_meta:
                    meta.update(opf_meta)
                
                # Extraer título interno
                internal_title = extract_internal_title(epub_bytes)
                if internal_title:
                    meta["internal_title"] = internal_title
                
                # Extraer filename title
                filename_title = unquote(urlparse(download_url).path.split("/")[-1]).replace(".epub", "")
                meta["filename_title"] = filename_title
                
                # Debug logging
                logger.info(f"FB Post Meta - internal_title: {meta.get('internal_title')}, collection_title: {meta.get('titulo_serie')}, titulo_volumen: {meta.get('titulo_volumen')}")
                
                # Generar caption completo (sin slug para FB)
                full_caption = formatear_mensaje_portada(meta, include_slug=False)
                
                # Usar el caption completo
                caption_base = full_caption
                
        except Exception as e:
            logger.warning(f"Could not fetch/parse EPUB for FB post: {e}")
            caption_base = f"📚 <b>{title}</b>" # Fallback
        
        caption = (
            f"{caption_base}\n\n"
            f"⬇️ <b>Descarga directa:</b>\n"
            f"{public_link}"
        )
        
        return {
            "caption": caption,
            "cover_url": cover_url,
            "public_link": public_link
        }

    except Exception as e:
        logger.error(f"Error preparing FB post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/facebook/publish")
async def publish_facebook_post(
    request: Request,
    current_uid: int = Depends(get_current_user)
):
    """
    Publica en el grupo de Facebook configurado.
    """
    if current_uid not in config.FACEBOOK_PUBLISHERS:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if not config.FACEBOOK_PAGE_ACCESS_TOKEN or not config.FACEBOOK_GROUP_ID:
         raise HTTPException(status_code=400, detail="Facebook credentials not configured")

    try:
        data = await request.json()
        caption = data.get('caption')
        cover_url = data.get('cover_url') # URL de la portada (debe ser pública para que FB la vea, o subimos bytes)
        
        # Nota: Para subir foto a FB, se puede pasar URL si es pública. 
        # Si nuestra URL de portada es local/proxy, FB podría no verla si no es pública real.
        # Asumimos que cover_url es accesible o usamos el proxy de imagen si es público.
        
        # Si la cover_url es relativa o interna, intentar resolverla
        if cover_url and not cover_url.startswith("http"):
             cover_url = f"{config.BASE_URL}{cover_url}"

        # Lógica de publicación en Graph API
        url = f"https://graph.facebook.com/{config.FACEBOOK_GROUP_ID}/photos"
        params = {
            "url": cover_url,
            "caption": caption.replace("<b>", "").replace("</b>", ""), # FB no soporta HTML tags básicos así
            "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, params=params, timeout=30)
            resp.raise_for_status()
            fb_data = resp.json()
            
        return {"success": True, "fb_id": fb_data.get("id")}

    except Exception as e:
        logger.error(f"Error publishing to FB: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_config(current_uid: int = Depends(get_current_user)):
    """
    Retorna configuración inicial para la Mini App, incluyendo permisos de admin.
    """
    is_admin = current_uid in config.ADMIN_USERS
    is_publisher = current_uid in config.FACEBOOK_PUBLISHERS
    
    response = {
        "is_admin": is_admin,
        "is_facebook_publisher": is_publisher,
        "admin_root_url": config.OPDS_ROOT_EVIL if is_admin else None,
        "destinations": []
    }
    
    if is_admin:
        # Destinos predefinidos para admins
        response["destinations"] = [
            {"name": "📍 Aquí (Chat privado)", "id": "me"},
            {"name": "📣 ZeePubs Channel", "id": "@ZeePubs"},
            {"name": "🤖 ZeePub Bot Test", "id": "@ZeePubBotTest"}
        ]
        
    return response

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
        target_chat_id = data.get('target_chat_id')
        
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
            cover_url=cover_url,
            target_chat_id=target_chat_id
        )
        
        if success:
            return {"status": "success", "message": "Download completed"}
        else:
            raise HTTPException(status_code=500, detail="Download failed")
            
    except Exception as e:
        logger.error(f"Error in download endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
