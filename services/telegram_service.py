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


async def send_photo_bytes(bot, chat_id, caption, data_or_path, filename="photo.jpg", parse_mode=None):
    """Envía foto desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption, parse_mode=parse_mode)
        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption, parse_mode=parse_mode)
    except Exception as e:
        logger.debug(f"Error send_photo_bytes: {e}")
    return None


async def send_doc_bytes(bot, chat_id, caption, data_or_path, filename="file.epub"):
    """Envía documento EPUB desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption)
        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption)
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
        destino = user_state.get("destino") or update.effective_chat.id
        chat_origen = user_state.get("chat_origen") or destino
        series_id = user_state.get("series_id")
        volume_id = user_state.get("volume_id")
        user_state["ultima_pagina"] = user_state.get("url", config.OPDS_ROOT_START)

        # Verificar límite antes de descargar
        if not can_download(uid):
            await bot.send_message(chat_id=destino, text="🚫 Has alcanzado tu límite de descargas por hoy.")
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
                                    "traductor", "sinopsis"):
                            if opf_meta.get(key):
                                meta[key] = opf_meta[key]
                except Exception as e:
                    logger.debug(f"publicar_libro: fallo parse OPF: {e}")
                
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
            portada_data, filename="cover.jpg", parse_mode="HTML"
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
            await bot.send_message(chat_id=destino, text=texto, parse_mode="HTML")
        else:
            slug = generar_slug_from_meta(meta)
            fallback = f"Sinopsis: (no disponible)\n#{slug}" if slug else "Sinopsis: (no disponible)"
            await bot.send_message(chat_id=destino, text=fallback)

        # Mostrar botones
        sent = await bot.send_message(
            chat_id=chat_origen,
            text="¿Deseas descargar este EPUB?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Descargar EPUB", callback_data="descargar_epub")],
                [InlineKeyboardButton("↩️ Volver", callback_data="volver_ultima")],
            ])
        )
        user_state["msg_botones_id"] = sent.message_id
        user_state["titulo_pendiente"] = titulo


async def descargar_epub_pendiente(update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    """Envía el EPUB guardado tras confirmación del usuario."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    epub_buffer = user_state.pop("epub_buffer", None)
    epub_url = user_state.pop("epub_url", "")
    meta = user_state.pop("meta_pendiente", {})
    titulo = user_state.pop("titulo_pendiente", "")
    msg_id = user_state.pop("msg_botones_id", None)
    destino = user_state.get("destino") or update.effective_chat.id
    chat_origen = user_state.get("chat_origen") or destino

    # Borrar botones
    if msg_id:
        try:
            await bot.delete_message(chat_id=chat_origen, message_id=msg_id)
        except:
            pass

    # Si eligió Volver, descartar buffer
    if update.callback_query.data == "volver_ultima":
        return

    # Verificar que hay EPUB disponible
    if not epub_buffer:
        await bot.send_message(chat_id=chat_origen, text="⚠️ EPUB no disponible.")
        return

    # Verificar cuota nuevamente
    if not can_download(uid):
        await bot.send_message(chat_id=destino, text="🚫 Límite de descargas alcanzado.")
        return

    # Preparar envío
    prep = await bot.send_message(chat_id=destino, text="⏳ Preparando archivo...")

    try:
        # Enviar EPUB
        fname = unquote(urlparse(epub_url).path.split("/")[-1]) or "archivo.epub"
        caption = (meta.get("titulo_volumen") or titulo or "").strip()
        slug = generar_slug_from_meta(meta)
        if slug:
            caption += f"\n#{slug}"
        
        await send_doc_bytes(bot, destino, caption, epub_buffer, filename=fname)

        # Registrar descarga
        record_download(uid)
        restantes = downloads_left(uid)

        # Mostrar descargas restantes (excepto Premium)
        if restantes != "ilimitadas":
            await bot.send_message(chat_id=destino, text=f"📥 Te quedan {restantes} descargas disponibles para hoy.")

        cleanup_tmp(epub_buffer)

    finally:
        # Eliminar mensaje de preparación
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
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
