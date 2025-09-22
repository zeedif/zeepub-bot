import logging
from urllib.parse import urlparse, unquote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from http.fetcher import fetch_bytes, cleanup_tmp
from telegram_utils.sender import send_photo_bytes, send_doc_bytes
from telegram_utils.formatter import generar_slug_from_meta, formatear_mensaje_portada, escapar_html
from opds.parser import obtener_metadatos_opds
from epub.opf_parser import parse_opf_from_epub
from epub.extractor import obtener_sinopsis_opds, obtener_sinopsis_opds_volumen
from config import OPDS_ROOT_START, OPDS_ROOT_EVIL
from . import ensure_user, user_state
from .navigation import mostrar_colecciones


async def set_destino(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    ensure_user(uid)
    _, destino = query.data.split("|", 1)

    if destino == "aqui":
        user_state[uid]["destino"] = update.effective_chat.id
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]" if root == OPDS_ROOT_EVIL else "📚 Todas las bibliotecas"
        await mostrar_colecciones(update, context, root, from_collection=False)

    elif destino in ["@ZeePubBotTest", "@ZeePubs"]:
        user_state[uid]["destino"] = destino
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]" if root == OPDS_ROOT_EVIL else "📚 Todas las bibliotecas"
        await mostrar_colecciones(update, context, root, from_collection=False)

    elif destino == "otro":
        user_state[uid]["esperando_destino_manual"] = True
        await query.edit_message_text("Escribe el @usuario o chat_id donde quieres publicar:")


async def publicar_libro(update_or_uid, context, uid: int, titulo: str, portada_url: str, epub_url: str, menu_prep: tuple = None):
    """
    Publica un libro: OPF > OPDS
    """
    bot = context.bot
    ensure_user(uid)
    destino = user_state[uid].get("destino") or user_state[uid].get("chat_origen")
    chat_origen = user_state[uid].get("chat_origen")
    series_id = user_state[uid].get("series_id")
    volume_id = user_state[uid].get("volume_id")
    root_url = user_state[uid].get("opds_root", OPDS_ROOT_START)
    ultima_url = user_state[uid].get("url", root_url)
    user_state[uid]["ultima_pagina"] = ultima_url

    meta = await obtener_metadatos_opds(series_id, volume_id)

    epub_downloaded = None
    opf_meta = None
    if epub_url:
        epub_downloaded = await fetch_bytes(epub_url, timeout=120)
        if epub_downloaded:
            try:
                opf_meta = await parse_opf_from_epub(epub_downloaded)
                if opf_meta:
                    if opf_meta.get("autores"):
                        meta["autores"] = opf_meta.get("autores") or meta.get("autores") or []
                        if opf_meta.get("autores"):
                            meta["autor"] = opf_meta.get("autores")[0] if opf_meta.get("autores") else meta.get("autor")
                    for key in ("titulo_serie", "titulo_volumen", "ilustrador", "categoria", "publisher", "publisher_url"):
                        if opf_meta.get(key):
                            meta[key] = opf_meta.get(key)
                    if opf_meta.get("generos"):
                        meta["generos"] = opf_meta.get("generos")
                    if opf_meta.get("demografia"):
                        meta["demografia"] = opf_meta.get("demografia")
                    if opf_meta.get("maquetadores"):
                        meta["maquetadores"] = opf_meta.get("maquetadores")
                    if opf_meta.get("traductor"):
                        meta["traductor"] = opf_meta.get("traductor")
                    if opf_meta.get("sinopsis"):
                        meta["sinopsis"] = opf_meta.get("sinopsis")
            except Exception as e:
                logging.debug("publicar_libro: fallo parse OPF desde epub: %s", e)

    slug = generar_slug_from_meta(meta)
    mensaje_portada = formatear_mensaje_portada(meta)

    if portada_url:
        result = await fetch_bytes(portada_url, timeout=15)
        try:
            await send_photo_bytes(bot, destino, mensaje_portada, result, filename="portada.jpg")
            if menu_prep and isinstance(menu_prep, tuple):
                try:
                    menu_chat, menu_msg_id = menu_prep
                    if menu_chat and menu_msg_id:
                        await bot.delete_message(chat_id=menu_chat, message_id=menu_msg_id)
                except Exception:
                    logging.debug("publicar_libro: no se pudo borrar menu_prep luego de enviar portada")
        finally:
            cleanup_tmp(result)

    sinopsis_texto = None
    if meta.get("sinopsis"):
        sinopsis_texto = meta.get("sinopsis")
    else:
        if series_id and volume_id:
            sinopsis_texto = await obtener_sinopsis_opds_volumen(series_id, volume_id)
        if not sinopsis_texto and series_id:
            try:
                sinopsis_texto = await obtener_sinopsis_opds(series_id)
            except Exception as e:
                logging.error("Error obteniendo sinopsis por serie: %s", e)

    if sinopsis_texto:
        sinopsis_esc = escapar_html(sinopsis_texto)
        sinopsis_suffix = f"\n#{slug}" if slug else ""
        mensaje = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>{sinopsis_suffix}"
        await bot.send_message(chat_id=destino, text=mensaje, parse_mode="HTML")
    else:
        if slug:
            await bot.send_message(chat_id=destino, text=f"Sinopsis: (no disponible)\n#{slug}")
        else:
            await bot.send_message(chat_id=destino, text="Sinopsis: (no disponible)")

    prep = await bot.send_message(chat_id=destino, text="⏳ Preparando archivo...")
    prep_msg_id = getattr(prep, "message_id", None)

    epub_to_send = epub_downloaded
    if not epub_to_send and epub_url:
        epub_to_send = await fetch_bytes(epub_url, timeout=120)

    if epub_to_send:
        try:
            nombre_archivo = unquote(urlparse(epub_url).path.split("/")[-1]) or "archivo.epub"
            caption_title = (meta.get("titulo_volumen") or titulo or "").strip()
            caption = caption_title + (f"\n#{slug}" if slug else "")
            await send_doc_bytes(bot, destino, caption, epub_to_send, filename=nombre_archivo)
        finally:
            cleanup_tmp(epub_to_send)

    if prep_msg_id:
        try:
            await bot.delete_message(chat_id=destino, message_id=prep_msg_id)
        except Exception:
            pass

    if menu_prep and isinstance(menu_prep, tuple):
        try:
            menu_chat, menu_msg_id = menu_prep
            if menu_chat and menu_msg_id:
                try:
                    await bot.delete_message(chat_id=menu_chat, message_id=menu_msg_id)
                except Exception:
                    pass
        except Exception:
            pass

    keyboard = [
        [InlineKeyboardButton("📚 Volver a categorías", callback_data="volver_colecciones")],
        [InlineKeyboardButton("↩️ Volver a la página anterior", callback_data="volver_ultima")],
        [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_temp = await bot.send_message(chat_id=chat_origen, text="¿Qué quieres hacer ahora?")
    msg_temp_id = getattr(msg_temp, "message_id", None)
    user_state[uid]["msg_que_hacer"] = msg_temp_id
    await bot.send_message(chat_id=chat_origen, text="Selecciona una opción:", reply_markup=reply_markup)