# services/opds_service.py

import uuid
import logging
from urllib.parse import urlparse, unquote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import state_manager
from config.config_settings import config
from utils.http_client import parse_feed_from_url
from utils.helpers import abs_url, find_zeepubs_destino

logger = logging.getLogger(__name__)

async def mostrar_colecciones(update, context: ContextTypes.DEFAULT_TYPE, url: str, from_collection: bool = False):
    """Mostrar colecciones o libros basados en un feed OPDS."""
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    feed = await parse_feed_from_url(url)
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if hasattr(update, "message") and update.message:
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return

    root_url = st.get("opds_root")
    st["ultima_pagina"] = url
    if from_collection:
        st.setdefault("historial", []).append((st.get("titulo", ""), st.get("url", root_url)))
    st.update({
        "url": url,
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None}
    })

    # enlaces de navegación
    for link in getattr(feed.feed, "links", []):
        rel = getattr(link, "rel", "")
        href = abs_url(config.BASE_URL, link.href)
        if rel == "previous":
            st["nav"]["prev"] = href
        elif rel == "next":
            st["nav"]["next"] = href
    if not st["nav"]["prev"] and st.get("historial"):
        st["nav"]["prev"] = st["historial"][-1][1]

    colecciones, libros = [], []
    ocultos = {"En el puente", "Listas de lectura", "Deseo leer", "Todas las colecciones"}
    for entry in feed.entries:
        title = getattr(entry, "title", "")
        author = getattr(entry, "author", "Desconocido")
        href_entry = getattr(entry, "link", "")
        href_sub, portada = None, None
        acqs = []
        for l in getattr(entry, "links", []):
            rel = getattr(l, "rel", "")
            href_l = abs_url(config.BASE_URL, l.href)
            if rel == "subsection":
                href_sub = href_l
            elif "acquisition" in rel:
                acqs.append(href_l)
            elif "image" in rel:
                portada = href_l

        if href_sub and title not in ocultos:
            colecciones.append({"titulo": title, "href": href_sub})
        elif acqs:
            for download in acqs:
                libros.append({
                    "titulo": title,
                    "autor": author,
                    "href": href_entry,
                    "descarga": download,
                    "portada": portada
                })

    # construir teclado
    keyboard = [[InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")]]
    if colecciones:
        for i, col in enumerate(colecciones):
            st["colecciones"][i] = col
            keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{i}")])
    else:
        for b in libros:
            key = uuid.uuid4().hex[:8]
            st["libros"][key] = b
            name = unquote(urlparse(b["descarga"]).path.split("/")[-1]).replace(".epub", "")
            keyboard.append([InlineKeyboardButton(name, callback_data=f"lib|{key}")])

    nav_buttons = []
    if st["nav"]["prev"]:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data="nav|prev"))
    if st["nav"]["next"]:
        nav_buttons.append(InlineKeyboardButton("➡️ Siguiente", callback_data="nav|next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Título y markup
    title = st.get("titulo") or "📚 Categorías"
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Enviar o editar mensaje
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(title, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(title, reply_markup=reply_markup)

async def buscar_zeepubs_directo(update, context, uid: int):
    """Acceso directo a ZeePubs [ES] detectándolo en el feed."""
    st = state_manager.get_user_state(uid)
    url = st.get("opds_root")
    logger.debug("Intentando acceso directo a ZeePubs desde %s", url)
    feed = await parse_feed_from_url(url)
    destino = find_zeepubs_destino(feed, prefer_libraries=True)
    if destino:
        st.update({"titulo": "📁 ZeePubs [ES]", "historial": []})
        await mostrar_colecciones(update, context, destino, from_collection=True)
    else:
        await mostrar_colecciones(update, context, url, from_collection=False)
