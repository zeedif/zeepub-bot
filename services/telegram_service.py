# services/telegram_service.py

import io
import os
import logging
from urllib.parse import urlparse, unquote
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import state_manager
from core.session_manager import session_manager
from config.config_settings import config
from services.metadata_service import (
    obtener_metadatos_opds,
    obtener_sinopsis_opds,
    obtener_sinopsis_opds_volumen,
)
from services.epub_service import parse_opf_from_epub
from utils.http_client import fetch_bytes, cleanup_tmp
from utils.helpers import generar_slug_from_meta, formatear_mensaje_portada, escapar_html
from utils.download_limiter import record_download, can_download, downloads_left
from services.epub_service import parse_opf_from_epub, extract_cover_from_epub

logger = logging.getLogger(__name__)


async def send_photo_bytes(bot, chat_id, caption, data_or_path, filename="cover.jpg", parse_mode=None, message_thread_id=None):
    """Envía imagen desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption, parse_mode=parse_mode, message_thread_id=message_thread_id)
        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption, parse_mode=parse_mode, message_thread_id=message_thread_id)
    except Exception as e:
        logger.debug(f"Error send_photo_bytes: {e}")
    return None


async def send_doc_bytes(bot, chat_id, caption, data_or_path, filename="file.epub", parse_mode=None, message_thread_id=None):
    """Envía documento EPUB desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption, parse_mode=parse_mode, message_thread_id=message_thread_id)
        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption, parse_mode=parse_mode, message_thread_id=message_thread_id)
    except Exception as e:
        logger.debug(f"Error send_doc_bytes: {e}")
    return None


async def publicar_libro(update, context: ContextTypes.DEFAULT_TYPE,
                         uid: int, titulo: str, portada_url: str,
                         epub_url: str, menu_prep: tuple = None):
    """Descarga EPUB para metadatos, muestra portada, sinopsis y botones."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    lock = session_manager.get_publish_lock(uid)
    
    async with lock:
        from utils.helpers import get_thread_id
        thread_id_origen = get_thread_id(update)
        
        destino = user_state.get("destino") or update.effective_chat.id
        chat_origen = user_state.get("chat_origen") or destino
        series_id = user_state.get("series_id")
        volume_id = user_state.get("volume_id")
        user_state["ultima_pagina"] = user_state.get("url", config.OPDS_ROOT_START)
        
        # Solo usar thread_id si destino == chat_origen
        thread_id_destino = thread_id_origen if destino == chat_origen else None

        # Verificar límite antes de descargar
        if not can_download(uid):
            await bot.send_message(
                chat_id=destino, 
                text="🚫 Has alcanzado tu límite de descargas por hoy.",
                message_thread_id=thread_id_destino
            )
            return

        # Obtener metadatos OPDS
        meta = await obtener_metadatos_opds(series_id, volume_id)

        # Descargar EPUB para parsear metadatos
        epub_downloaded = None
        if epub_url:
            epub_downloaded = await fetch_bytes(epub_url, timeout=120)
            if epub_downloaded:
                try:
                    opf_meta = await parse_opf_from_epub(epub_downloaded)
                    if opf_meta:
                        if opf_meta.get("autores"):
                            meta["autores"] = opf_meta["autores"]
                            meta["autor"] = opf_meta["autores"][0]
                        for key in ("titulo_serie", "titulo_volumen", "ilustrador",
                                    "categoria", "publisher", "publisher_url",
                                    "generos", "demografia", "maquetadores",
                                    "traductor", "sinopsis", "epub_version",
                                    "fecha_modificacion", "fecha_publicacion"):
                            if opf_meta.get(key):
                                meta[key] = opf_meta[key]
                except Exception as e:
                    logger.debug(f"publicar_libro: fallo parse OPF: {e}")
                
                # Extraer título interno y nombre de archivo para nuevo formato
                try:
                    from services.epub_service import extract_internal_title
                    internal_title = extract_internal_title(epub_downloaded)
                    if internal_title:
                        meta["internal_title"] = internal_title
                    
                    # Extraer filename_title del epub_url
                    from urllib.parse import unquote, urlparse
                    filename_title = unquote(urlparse(epub_url).path.split("/")[-1]).replace(".epub", "")
                    meta["filename_title"] = filename_title
                except Exception as e:
                    logger.debug(f"publicar_libro: fallo extra metadata: {e}")
                
                # Guardar EPUB y metadatos para envío posterior
                user_state["epub_buffer"] = epub_downloaded
                user_state["epub_url"] = epub_url
                user_state["meta_pendiente"] = meta

        # Dentro de publicar_libro, donde quieras enviar portada:
        mensaje_portada = formatear_mensaje_portada(meta)

        # Extraer portada embebida
        cover_bytes = None
        if epub_downloaded:
            cover_bytes = extract_cover_from_epub(epub_downloaded)

        # Fallback a URL OPDS
        if cover_bytes:
            portada_data = cover_bytes
        else:
            portada_data = await fetch_bytes(portada_url, timeout=15)

        await send_photo_bytes(
            bot, destino, mensaje_portada,
            portada_data, filename="cover.jpg", parse_mode="HTML",
            message_thread_id=thread_id_destino
        )

        if not cover_bytes:
            cleanup_tmp(portada_data)

        # Sinopsis
        sinopsis = meta.get("sinopsis")
        if not sinopsis:
            if series_id and volume_id:
                sinopsis = await obtener_sinopsis_opds_volumen(series_id, volume_id)
            if not sinopsis and series_id:
                try:
                    sinopsis = await obtener_sinopsis_opds(series_id)
                except Exception as e:
                    logger.error(f"Error sinopsis OPDS: {e}")
        
        if sinopsis:
            sinopsis_esc = escapar_html(sinopsis)
            texto = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>\n#{generar_slug_from_meta(meta)}"
            await bot.send_message(
                chat_id=destino, 
                text=texto, 
                parse_mode="HTML",
                message_thread_id=thread_id_destino
            )
        else:
            slug = generar_slug_from_meta(meta)
            fallback = f"Sinopsis: (no disponible)\n#{slug}" if slug else "Sinopsis: (no disponible)"
            await bot.send_message(
                chat_id=destino, 
                text=fallback,
                message_thread_id=thread_id_destino
            )

        # Mostrar botones
        # Calcular tamaño y versión para el mensaje de confirmación
        if epub_downloaded:
            # Calcular tamaño: fetch_bytes puede devolver bytes o ruta de archivo
            if isinstance(epub_downloaded, (bytes, bytearray)):
                size_mb = len(epub_downloaded) / (1024 * 1024)
            elif isinstance(epub_downloaded, str) and os.path.exists(epub_downloaded):
                size_mb = os.path.getsize(epub_downloaded) / (1024 * 1024)
            else:
                size_mb = 0.0
                
            version = meta.get("epub_version", "2.0")
            fecha = meta.get("fecha_modificacion", "Desconocida")
            titulo_vol = meta.get("titulo_volumen") or titulo or "Desconocido"
            
            info_text = (
                f"📂 <b>{titulo_vol}</b>\n"
                f"ℹ️ Versión Epub: {version}\n"
                f"📅 Actualizado: {fecha}\n"
                f"📦 Tamaño: {size_mb:.2f} MB"
            )
            
            # Enviar mensaje de información separado (siempre en chat_origen con thread_id)
            msg_info = await bot.send_message(
                chat_id=chat_origen,
                text=info_text,
                parse_mode="HTML",
                message_thread_id=thread_id_origen
            )
            user_state["msg_info_id"] = msg_info.message_id

        keyboard = [
            [InlineKeyboardButton("📥 Descargar EPUB", callback_data="descargar_epub")],
        ]
        
        # Botón Facebook para publishers
        if uid in config.FACEBOOK_PUBLISHERS:
            keyboard.append([InlineKeyboardButton("📝 Post FB", callback_data="preparar_post_fb")])
            
        keyboard.append([InlineKeyboardButton("↩️ Volver", callback_data="volver_ultima")])

        sent = await bot.send_message(
            chat_id=chat_origen,
            text="¿Deseas descargar este EPUB?",
            parse_mode="HTML",
            message_thread_id=thread_id_origen,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        user_state["msg_botones_id"] = sent.message_id
        user_state["titulo_pendiente"] = titulo


async def descargar_epub_pendiente(update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    """Envía el EPUB guardado tras confirmación del usuario."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    
    from utils.helpers import get_thread_id
    thread_id_origen = user_state.get("message_thread_id")  # Usar el guardado en el estado
    
    epub_buffer =user_state.pop("epub_buffer", None)
    epub_url = user_state.pop("epub_url", "")
    meta = user_state.pop("meta_pendiente", {})
    titulo = user_state.pop("titulo_pendiente", "")
    msg_id = user_state.pop("msg_botones_id", None)
    msg_info_id = user_state.pop("msg_info_id", None)
    destino = user_state.get("destino") or update.effective_chat.id
    chat_origen = user_state.get("chat_origen") or destino
    
    # Solo usar thread_id si destino == chat_origen
    thread_id_destino = thread_id_origen if destino == chat_origen else None

    # Borrar botones y mensaje de info
    if msg_id:
        try:
            await bot.delete_message(chat_id=chat_origen, message_id=msg_id)
        except:
            pass
    if msg_info_id:
        try:
            await bot.delete_message(chat_id=chat_origen, message_id=msg_info_id)
        except:
            pass

    # Si eligió Volver, descartar buffer
    if update.callback_query.data == "volver_ultima":
        return

    # Verificar que hay EPUB disponible
    if not epub_buffer:
        await bot.send_message(
            chat_id=chat_origen, 
            text="⚠️ EPUB no disponible.",
            message_thread_id=thread_id_origen
        )
        return

    # Verificar cuota nuevamente
    if not can_download(uid):
        await bot.send_message(
            chat_id=destino, 
            text="🚫 Límite de descargas alcanzado.",
            message_thread_id=thread_id_destino
        )
        return

    # Preparar envío
    prep = await bot.send_message(
        chat_id=destino, 
        text="⏳ Preparando archivo...",
        message_thread_id=thread_id_destino
    )

    try:
        # Enviar EPUB
        fname = unquote(urlparse(epub_url).path.split("/")[-1]) or "archivo.epub"
        
        # Calcular tamaño: epub_buffer puede ser bytes o ruta de archivo
        if isinstance(epub_buffer, (bytes, bytearray)):
            size_mb = len(epub_buffer) / (1024 * 1024)
        elif isinstance(epub_buffer, str) and os.path.exists(epub_buffer):
            size_mb = os.path.getsize(epub_buffer) / (1024 * 1024)
        else:
            size_mb = 0.0
        version = meta.get("epub_version", "2.0") # Default a 2.0 si no se encuentra
        fecha = meta.get("fecha_modificacion", "Desconocida")
        titulo_vol = meta.get("titulo_volumen") or titulo or "Desconocido"
        
        caption = (
            f"📂 <b>{titulo_vol}</b>\n"
            f"ℹ️ Versión Epub: {version}\n"
            f"📅 Actualizado: {fecha}\n"
            f"📦 Tamaño: {size_mb:.2f} MB"
        )
        
        slug = generar_slug_from_meta(meta)
        if slug:
            caption += f"\n#{slug}"
        
        await send_doc_bytes(
            bot, destino, caption, epub_buffer, filename=fname, parse_mode="HTML",
            message_thread_id=thread_id_destino
        )

        # Registrar descarga
        record_download(uid)
        restantes = downloads_left(uid)

        # Mostrar descargas restantes (excepto Premium)
        if restantes != "ilimitadas":
            await bot.send_message(
                chat_id=destino, 
                text=f"📥 Te quedan {restantes} descargas disponibles para hoy.",
                message_thread_id=thread_id_destino
            )

        cleanup_tmp(epub_buffer)

    finally:
        # Eliminar mensaje de preparación
        if prep:
            try:
                await bot.delete_message(chat_id=destino, message_id=prep.message_id)
            except:
                pass

    # Mostrar opciones finales
    keyboard = [
        [InlineKeyboardButton("📚 Volver a categorías", callback_data="volver_colecciones")],
        [InlineKeyboardButton("↩️ Volver a la página anterior", callback_data="volver_ultima")],
        [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")],
    ]
    await bot.send_message(
        chat_id=chat_origen,
        text="Selecciona una opción:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id_origen
    )


async def enviar_libro_directo(bot, user_id: int, title: str, download_url: str, cover_url: str = None, target_chat_id: int = None):
    """
    Descarga y envía un libro directamente al usuario (para la Mini App).
    Replica el formato del bot: Portada -> Sinopsis -> Archivo.
    """
    try:
        # 1. Verificar límite
        if not can_download(user_id):
            await bot.send_message(chat_id=user_id, text="🚫 Has alcanzado tu límite de descargas por hoy.")
            return False

        # 2. Mensaje de preparación (siempre al usuario que interactúa)
        prep_msg = await bot.send_message(chat_id=user_id, text=f"⏳ Procesando descarga de: {title}...")

        # Destino final del libro
        destino = target_chat_id if target_chat_id else user_id

        # 3. Descargar EPUB
        epub_bytes = await fetch_bytes(download_url, timeout=120)
        if not epub_bytes:
            await bot.send_message(chat_id=user_id, text="❌ Error al descargar el archivo desde la fuente.")
            return False

        # 4. Parsear metadatos del EPUB
        meta = {"titulo": title, "epub_version": "2.0", "fecha_modificacion": "Desconocida"}
        try:
            opf_meta = await parse_opf_from_epub(epub_bytes)
            if opf_meta:
                meta.update(opf_meta)
                if opf_meta.get("autores"):
                    meta["autor"] = opf_meta["autores"][0]
        except Exception as e:
            logger.error(f"Error parsing OPF in direct download: {e}")

        # Extraer título interno y nombre de archivo para nuevo formato
        try:
            from services.epub_service import extract_internal_title
            internal_title = extract_internal_title(epub_bytes)
            if internal_title:
                meta["internal_title"] = internal_title
        except Exception as e:
            logger.debug(f"enviar_libro_directo: fallo extra metadata: {e}")

        # 5. Enviar Portada
        # Intentar extraer del EPUB primero
        cover_bytes = extract_cover_from_epub(epub_bytes)
        portada_data = cover_bytes if cover_bytes else (await fetch_bytes(cover_url) if cover_url else None)
        
        if portada_data:
            mensaje_portada = formatear_mensaje_portada(meta)
            await send_photo_bytes(bot, destino, mensaje_portada, portada_data, filename="cover.jpg", parse_mode="HTML")
            if not cover_bytes: # Si bajamos la portada de URL, limpiar si fuera archivo temporal (fetch_bytes devuelve bytes, asi que no aplica cleanup_tmp igual que archivo)
                pass 

        # 6. Enviar Sinopsis
        sinopsis = meta.get("sinopsis")
        if sinopsis:
            sinopsis_esc = escapar_html(sinopsis)
            texto = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>\n#{generar_slug_from_meta(meta)}"
            await bot.send_message(chat_id=destino, text=texto, parse_mode="HTML")

        # 7. Enviar Archivo EPUB
        # Calcular tamaño
        if isinstance(epub_bytes, (bytes, bytearray)):
            size_mb = len(epub_bytes) / (1024 * 1024)
        elif isinstance(epub_bytes, str) and os.path.exists(epub_bytes):
            size_mb = os.path.getsize(epub_bytes) / (1024 * 1024)
        else:
            size_mb = 0.0
        version = meta.get("epub_version", "2.0")
        fecha = meta.get("fecha_modificacion", "Desconocida")
        titulo_vol = meta.get("titulo_volumen") or meta.get("titulo") or title
        
        caption = (
            f"📂 <b>{titulo_vol}</b>\n"
            f"ℹ️ Versión Epub: {version}\n"
            f"📅 Actualizado: {fecha}\n"
            f"📦 Tamaño: {size_mb:.2f} MB"
        )
        
        slug = generar_slug_from_meta(meta)
        if slug:
            caption += f"\n#{slug}"

        # Nombre de archivo desde URL (igual que en descargar_epub_pendiente)
        fname = unquote(urlparse(download_url).path.split("/")[-1]) or "archivo.epub"
        
        await send_doc_bytes(bot, destino, caption, epub_bytes, filename=fname, parse_mode="HTML")

        # 8. Registrar descarga y notificar
        record_download(user_id)
        restantes = downloads_left(user_id)
        if restantes != "ilimitadas":
            await bot.send_message(chat_id=user_id, text=f"📥 Te quedan {restantes} descargas disponibles para hoy.")

        # Limpieza
        try:
            await bot.delete_message(chat_id=user_id, message_id=prep_msg.message_id)
        except:
            pass
            
        return True

    except Exception as e:
        logger.error(f"Error en enviar_libro_directo: {e}", exc_info=True)
        await bot.send_message(chat_id=user_id, text=f"❌ Ocurrió un error interno: {str(e)}")
        return False


async def preparar_post_facebook(update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    """Genera vista previa del post de Facebook."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    
    # Recuperar datos del estado
    meta = user_state.get("meta_pendiente", {})
    epub_url = user_state.get("epub_url", "")
    titulo = user_state.get("titulo_pendiente", "")
    
    if not epub_url:
        await bot.send_message(chat_id=uid, text="❌ No hay libro seleccionado.")
        return

    # Construir link público acortado con SHA256 persistente
    from utils.url_cache import create_short_url
    from urllib.parse import quote
    
    dl_domain = config.DL_DOMAIN.rstrip('/')
    if not dl_domain.startswith("http"):
        dl_domain = f"https://{dl_domain}"
    
    # Crear hash y guardar en BD (persistente) con metadata del libro
    try:
        url_hash = create_short_url(epub_url, book_title=titulo)
    except Exception as e:
        logger.error("Error creando short URL: %s", e)
        await bot.send_message(chat_id=uid, text="❌ No fue posible generar el enlace acortado. Intenta de nuevo más tarde.")
        return
    public_link = f"{dl_domain}/api/dl/{url_hash}"
    
    # Usar formatear_mensaje_portada para generar el caption completo (sin slug)
    full_caption = formatear_mensaje_portada(meta, include_slug=False)
    
    # Info adicional del archivo
    epub_buffer = user_state.get("epub_buffer")
    if epub_buffer:
        if isinstance(epub_buffer, (bytes, bytearray)):
            size_mb = len(epub_buffer) / (1024 * 1024)
        elif isinstance(epub_buffer, str) and os.path.exists(epub_buffer):
            size_mb = os.path.getsize(epub_buffer) / (1024 * 1024)
        else:
            size_mb = 0.0
    else:
        size_mb = 0.0
    
    version = meta.get("epub_version", "2.0")
    fecha_mod = meta.get("fecha_modificacion", "Desconocida")
    
    # Construir caption con el formato completo + info del archivo + link
    caption = (
        f"{full_caption}\n\n"
        f"ℹ️ Versión Epub: {version}\n"
        f"📅 Actualizado: {fecha_mod}\n"
        f"📦 Tamaño: {size_mb:.2f} MB\n\n"
        f"⬇️ Descarga: {public_link}"
    )
    
    # Guardar en estado para publicación
    user_state["fb_caption"] = caption
    # La portada ya se envió antes, pero para publicar necesitamos URL o reusar bytes.
    # Si tenemos bytes en epub_buffer, podemos reusarlos.
    # Si no, usamos portada_url si existe.
    # Para simplificar, en la acción de publicar usaremos la URL de portada si es pública,
    # o re-extraeremos del buffer si es necesario.
    
    # Enviar vista previa
    btns = []
    if config.FACEBOOK_PAGE_ACCESS_TOKEN and config.FACEBOOK_GROUP_ID:
        btns.append([InlineKeyboardButton("🚀 Publicar ahora", callback_data="publicar_fb")])
    
    btns.append([InlineKeyboardButton("🗑️ Descartar", callback_data="descartar_fb")])
    
    # Enviar como mensaje nuevo
    await bot.send_message(
        chat_id=uid,
        text=f"📝 <b>Vista Previa Facebook:</b>\n\n{caption}",
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(btns)
    )

async def publicar_facebook_action(update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    """Publica el post en Facebook."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    caption = user_state.get("fb_caption")
    
    if not caption:
        await bot.send_message(chat_id=uid, text="❌ No hay post preparado.")
        return
        
    # Intentar obtener portada
    epub_buffer = user_state.get("epub_buffer")
    cover_bytes = None
    if epub_buffer:
        cover_bytes = extract_cover_from_epub(epub_buffer)
        
    if not cover_bytes:
        await bot.send_message(chat_id=uid, text="⚠️ No se pudo obtener la portada para subir a Facebook.")
        return

    # Subir a Facebook usando Graph API
    import httpx
    
    msg = await bot.send_message(chat_id=uid, text="⏳ Publicando en Facebook...")
    
    try:
        url = f"https://graph.facebook.com/{config.FACEBOOK_GROUP_ID}/photos"
        
        # Limpiar caption de HTML para FB
        clean_caption = caption.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        
        data = {
            "caption": clean_caption,
            "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
            "published": "true"
        }
        
        # Enviar archivo
        files = {"source": ("cover.jpg", io.BytesIO(cover_bytes), "image/jpeg")}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, files=files, timeout=60)
            resp.raise_for_status()
            fb_res = resp.json()
            
        await bot.edit_message_text(
            chat_id=uid, 
            message_id=msg.message_id, 
            text=f"✅ Publicado exitosamente!\nID: {fb_res.get('id')}"
        )
        
    except Exception as e:
        logger.error(f"Error publicando en FB: {e}")
        await bot.edit_message_text(
            chat_id=uid, 
            message_id=msg.message_id, 
            text=f"❌ Error al publicar: {str(e)}"
        )
