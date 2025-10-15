import logging
import uuid
from urllib.parse import urlparse, unquote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.config_settings import config
from core.state_manager import state_manager
from utils.helpers import abs_url, norm_string, find_zeepubs_destino
from utils.http_client import parse_feed_from_url

logger = logging.getLogger(__name__)

async def mostrar_colecciones(update, context, url: str, from_collection: bool = False):
    uid = update.effective_user.id
    user_state = state_manager.get_user_state(uid)

    feed = await parse_feed_from_url(url)
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if getattr(update, "message", None):
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return

    root_url = user_state.get("opds_root", config.OPDS_ROOT_START)

    state_manager.update_user_state(uid, {"ultima_pagina": url})

    if from_collection:
        titulo_actual = user_state.get("titulo", getattr(feed, "feed", {}).get("title", ""))
        url_actual = user_state.get("url", root_url)
        user_state["historial"].append((titulo_actual, url_actual))

    user_state.update({
        "url": url,
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None}
    })

    colecciones = []
    libros = []

    for link in getattr(feed.feed, "links", []):
        rel = getattr(link, "rel", "")
        href = abs_url(config.BASE_URL, link.href)
        if rel == "next":
            user_state["nav"]["next"] = href
        elif rel == "previous":
            user_state["nav"]["prev"] = href

    if not user_state["nav"]["prev"] and user_state["historial"]:
        _, prev_url = user_state["historial"][-1]
        user_state["nav"]["prev"] = prev_url

    ocultar_titulos = {"En el puente", "Listas de lectura", "Deseo leer", "Todas las colecciones"}

    for entry in feed.entries:
        titulo_entry = getattr(entry, "title", "")
        autor_entry = getattr(entry, "author", "Desconocido")
        href_entry = getattr(entry, "link", "")

        href_sub = None
        portada_url = None
        acquisition_links = []

        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = abs_url(config.BASE_URL, getattr(link, "href", ""))

            if rel == "subsection":
                href_sub = href
            if "acquisition" in rel:
                acquisition_links.append((href, link))
            if "image" in rel:
                portada_url = href

        if href_sub:
            if titulo_entry.strip() not in ocultar_titulos:
                colecciones.append({"titulo": titulo_entry, "href": href_sub})
        elif acquisition_links:
            for idx_acq, (acq_href, acq_link) in enumerate(acquisition_links):
                datos_libro = {
                    "titulo": titulo_entry,
                    "autor": autor_entry,
                    "href": href_entry,
                    "descarga": acq_href
                }
                if portada_url:
                    datos_libro["portada"] = portada_url
                libros.append(datos_libro)

    keyboard = []
    keyboard.append([InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")])

    for idx, col in enumerate(colecciones):
        user_state["colecciones"][idx] = col
        titulo_normalizado = col["titulo"].strip().lower()

        # NO navegar automáticamente en "Todas las bibliotecas"
        # Solo agregar botón normal
        keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{idx}")])

    if libros:
        for libro in libros:
            key = uuid.uuid4().hex[:8]
            user_state["libros"][key] = libro
            nombre_archivo = unquote(urlparse(libro.get("descarga", "")).path.split("/")[-1])
            volumen = nombre_archivo.replace(".epub", "").strip()
            keyboard.append([InlineKeyboardButton(volumen, callback_data=f"lib|{key}")])

    nav_buttons = []
    if user_state["nav"]["prev"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Anterior", callback_data="nav|prev"))
    if user_state["nav"]["next"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Siguiente", callback_data="nav|next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    titulo_mostrar = user_state.get("titulo", getattr(feed.feed, "title", ""))
    reply_markup = InlineKeyboardMarkup(keyboard)

    if getattr(update, "message", None):
        await update.message.reply_text(titulo_mostrar, reply_markup=reply_markup)
    else:
        current_message_text = update.callback_query.message.text or ""
        current_reply_markup = update.callback_query.message.reply_markup

        markup_unchanged = current_reply_markup == reply_markup
        text_unchanged = current_message_text == titulo_mostrar

        if text_unchanged and markup_unchanged:
            await update.callback_query.answer()
        else:
            await update.callback_query.edit_message_text(titulo_mostrar, reply_markup=reply_markup)

async def buscar_zeepubs_directo(update, context, uid: int):
    user_state = state_manager.get_user_state(uid)
    root_url = user_state.get("opds_root", config.OPDS_ROOT_START)

    logger.debug(f"buscar_zeepubs_directo: uid={uid} root_url={root_url}")

    feed = await parse_feed_from_url(root_url)
    if not feed:
        logger.debug(f"buscar_zeepubs_directo: no se pudo parsear feed desde {root_url}")
        await mostrar_colecciones(update, context, root_url, from_collection=False)
        return

    feed_title = getattr(feed, "feed", {}).get("title", None)
    logger.debug(f"buscar_zeepubs_directo: feed.title={feed_title!r}, entries={len(getattr(feed, 'entries', []))}")

    destino_href = find_zeepubs_destino(feed)

    if not destino_href and root_url != config.OPDS_ROOT_START:
        logger.debug(f"buscar_zeepubs_directo: reintentando con OPDS_ROOT_START {config.OPDS_ROOT_START}")
        feed_root_prim = await parse_feed_from_url(config.OPDS_ROOT_START)
        if feed_root_prim:
            logger.debug(f"buscar_zeepubs_directo: root principal feed.title={getattr(feed_root_prim, 'feed', {}).get('title', None)!r} entries={len(getattr(feed_root_prim, 'entries', []))}")
            destino_href = find_zeepubs_destino(feed_root_prim)

    if destino_href:
        logger.debug(f"buscar_zeepubs_directo: destino encontrado {destino_href}")
        state_manager.update_user_state(uid, {
            "titulo": "📁 ZeePubs [ES]",
            "historial": [],
            "libros": {},
            "colecciones": {},
            "nav": {"prev": None, "next": None}
        })
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
        return

    logger.debug(f"buscar_zeepubs_directo: no se encontró ZeePubs, mostrando root {root_url}")
    await mostrar_colecciones(update, context, root_url, from_collection=False)
