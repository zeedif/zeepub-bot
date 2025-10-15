import os
import io
import html
import logging
from urllib.parse import urlparse, unquote
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup

from config.config_settings import config
from core.state_manager import state_manager
from core.session_manager import session_manager
from services.metadata_service import obtener_metadatos_opds, obtener_sinopsis_opds, obtener_sinopsis_opds_volumen
from services.epub_service import parse_opf_from_epub
from utils.helpers import generar_slug_from_meta, formatear_mensaje_portada
from utils.http_client import fetch_bytes
from utils.decorators import cleanup_tmp
from utils.download_limiter import can_download

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

async def send_photo_bytes(bot, chat_id, caption, data_or_path, filename="photo.jpg"):
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption)

        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption)
        else:
            return None
    except Exception as e:
        logger.warning(f"Error send_photo_bytes: {e}")
        return None

async def send_doc_bytes(bot, chat_id, caption, data_or_path, filename="file.epub"):
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
        else:
            return None
    except Exception as e:
        logger.warning(f"Error send_doc_bytes: {e}")
        return None

async def publicar_libro(update_or_uid, context, uid: int, titulo: str,
                         portada_url: str, epub_url: str, menu_prep: tuple = None):
    bot = context.bot
    user_state = state_manager.get_user_state(uid)

    lock = session_manager.get_publish_lock(uid)
    async with lock:
        try:
            destino = user_state.get("destino") or user_state.get("chat_origen")
            chat_origen = user_state.get("chat_origen")

            if not can_download(uid):
                await bot.send_message(chat_id=destino,
                    text=f"🚫 Has alcanzado el límite de descargas en esta hora. Intenta más tarde.")
                return

            series_id = user_state.get("series_id")
            volume_id = user_state.get("volume_id")
            root_url = user_state.get("opds_root", config.OPDS_ROOT_START)
            ultima_url = user_state.get("url", root_url)

            state_manager.update_user_state(uid, {"ultima_pagina": ultima_url})

            meta = await obtener_metadatos_opds(series_id, volume_id)

            epub_downloaded = None
            opf_meta = None
            if epub_url:
                try:
                    epub_downloaded = await fetch_bytes(epub_url, timeout=180)
                    if epub_downloaded:
                        opf_meta = await parse_opf_from_epub(epub_downloaded)
                        if opf_meta:
                            if opf_meta.get("autores"):
                                meta["autores"] = opf_meta["autores"]
                                meta["autor"] = opf_meta["autores"][0]
                            for key in ("titulo_serie", "titulo_volumen", "ilustrador",
                                        "categoria", "publisher", "publisher_url"):
                                if opf_meta.get(key):
                                    meta[key] = opf_meta[key]
                            if opf_meta.get("generos"):
                                meta["generos"] = opf_meta["generos"]
                            if opf_meta.get("demografia"):
                                meta["demografia"] = opf_meta["demografia"]
                            if opf_meta.get("maquetadores"):
                                meta["maquetadores"] = opf_meta["maquetadores"]
                            if opf_meta.get("traductor"):
                                meta["traductor"] = opf_meta["traductor"]
                            if opf_meta.get("sinopsis"):
                                meta["sinopsis"] = opf_meta["sinopsis"]
                except Exception as e:
                    logger.warning(f"Error al descargar o parsear EPUB: {e}")

            slug = generar_slug_from_meta(meta)
            mensaje_portada = formatear_mensaje_portada(meta)

            sent_photo = None
            if portada_url:
                tmp = None
                try:
                    tmp = await fetch_bytes(portada_url, timeout=15)
                    sent_photo = await send_photo_bytes(bot, destino, mensaje_portada, tmp, filename="portada.jpg")
                except Exception as e:
                    logger.warning(f"Error enviando portada: {e}")
                finally:
                    if tmp:
                        cleanup_tmp(tmp)

                if menu_prep:
                    menu_chat, menu_msg_id = menu_prep
                    try:
                        await bot.delete_message(chat_id=menu_chat, message_id=menu_msg_id)
                    except Exception:
                        pass

            sinopsis_texto = meta.get("sinopsis")
            if not sinopsis_texto:
                if series_id and volume_id:
                    sinopsis_texto = await obtener_sinopsis_opds_volumen(series_id, volume_id)
                if not sinopsis_texto and series_id:
                    sinopsis_texto = await obtener_sinopsis_opds(series_id)

            if sinopsis_texto:
                try:
                    sinopsis_esc = html.escape(sinopsis_texto)
                    texto = (
                        "<b>Sinopsis:</b>\n"
                        f"<blockquote>{sinopsis_esc}</blockquote>"
                        + (f"\n#{slug}" if slug else "")
                    )
                    await bot.send_message(chat_id=destino, text=texto, parse_mode="HTML")
                except Exception:
                    pass
            else:
                try:
                    fallback = f"Sinopsis: (no disponible){'\\n' + '#' + slug if slug else ''}"
                    await bot.send_message(chat_id=destino, text=fallback)
                except Exception:
                    pass

            prep = None
            prep_id = None
            try:
                prep = await bot.send_message(chat_id=destino, text="⏳ Preparando archivo...")
                prep_id = prep.message_id
            except Exception:
                pass

            archivo = epub_downloaded or None
            if archivo:
                try:
                    fname = unquote(os.path.basename(urlparse(epub_url).path)) or "archivo.epub"
                    caption = (meta.get("titulo_volumen") or titulo).strip()
                    if slug:
                        caption += f"\n#{slug}"
                    await send_doc_bytes(bot, destino, caption, archivo, filename=fname)
                finally:
                    cleanup_tmp(archivo)

            if prep and prep_id:
                try:
                    await bot.delete_message(chat_id=destino, message_id=prep_id)
                except Exception:
                    pass

            kb = [
                [InlineKeyboardButton("📚 Volver a categorías", callback_data="volver_colecciones")],
                [InlineKeyboardButton("↩️ Volver a la página anterior", callback_data="volver_ultima")],
                [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")],
            ]
            msg = await bot.send_message(chat_id=chat_origen, text="¿Qué quieres hacer ahora?")
            state_manager.update_user_state(uid, {"msg_que_hacer": msg.message_id})
            await bot.send_message(
                chat_id=chat_origen,
                text="Selecciona una opción:",
                reply_markup=InlineKeyboardMarkup(kb)
            )

        except Exception:
            pass
