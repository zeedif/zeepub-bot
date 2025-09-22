import re
import logging
from urllib.parse import urlparse, unquote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import BASE_URL, OPDS_ROOT_START, OPDS_ROOT_EVIL
from opds.parser import parse_feed_from_url
from opds.helpers import abs_url, norm_string
from . import ensure_user, user_state
from .publish import publicar_libro


async def mostrar_colecciones(update, context: ContextTypes.DEFAULT_TYPE, url: str, from_collection: bool = False):
    uid = update.effective_user.id
    ensure_user(uid)
    feed = await parse_feed_from_url(url)
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if getattr(update, "message", None):
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return

    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
    user_state[uid]["ultima_pagina"] = url
    if from_collection:
        titulo_actual = user_state[uid].get("titulo", getattr(feed, "feed", {}).get("title", ""))
        url_actual = user_state[uid].get("url", root_url)
        user_state[uid]["historial"].append((titulo_actual, url_actual))

    user_state[uid]["url"] = url
    user_state[uid]["libros"] = {}
    user_state[uid]["colecciones"] = {}
    user_state[uid]["nav"] = {"prev": None, "next": None}

    colecciones, libros = [], []

    for link in getattr(feed.feed, "links", []):
        rel = getattr(link, "rel", "")
        href = abs_url(BASE_URL, link.href)
        if rel == "next":
            user_state[uid]["nav"]["next"] = href
        elif rel == "previous":
            user_state[uid]["nav"]["prev"] = href

    if not user_state[uid]["nav"]["prev"] and user_state[uid]["historial"]:
        _, prev_url = user_state[uid]["historial"][-1]
        user_state[uid]["nav"]["prev"] = prev_url

    ocultar_titulos = {"En el puente", "Listas de lectura", "Deseo leer", "Todas las colecciones"}

    for entry in feed.entries:
        titulo_entry = getattr(entry, "title", "")
        autor_entry = getattr(entry, "author", "Desconocido")
        href_entry = getattr(entry, "link", "")

        href_sub, portada_url = None, None
        acquisition_links = []

        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = abs_url(BASE_URL, getattr(link, "href", ""))
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

    if colecciones:
        for idx, col in enumerate(colecciones):
            user_state[uid]["colecciones"][idx] = col
            titulo_normalizado = col["titulo"].strip().lower()
            if titulo_normalizado == "todas las bibliotecas":
                if user_state.get(uid, {}).get("opds_root_base") != OPDS_ROOT_EVIL:
                    keyboard.append([InlineKeyboardButton("📚 Ingresar a Biblioteca", callback_data="abrir_zeepubs")])
                else:
                    keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{idx}")])
            else:
                keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{idx}")])
    elif libros:
        for libro in libros:
            from uuid import uuid4
            key = uuid4().hex[:8]
            user_state[uid]["libros"][key] = libro
            nombre_archivo = unquote(urlparse(libro.get("descarga", "")).path.split("/")[-1])
            volumen = nombre_archivo.replace(".epub", "").strip()
            keyboard.append([InlineKeyboardButton(volumen, callback_data=f"lib|{key}")])

    nav_buttons = []
    if user_state[uid]["nav"]["prev"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Anterior", callback_data="nav|prev"))
    if user_state[uid]["nav"]["next"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Siguiente", callback_data="nav|next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    titulo_mostrar = user_state[uid].get("titulo", getattr(feed.feed, "title", ""))
    reply_markup = InlineKeyboardMarkup(keyboard)
    if getattr(update, "message", None):
        await update.message.reply_text(titulo_mostrar, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(titulo_mostrar, reply_markup=reply_markup)


async def abrir_zeepubs(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    ensure_user(uid)

    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)

    def norm(s: str) -> str:
        return " ".join((s or "").split()).casefold()

    feed_root = await parse_feed_from_url(root_url)
    destino_href = None

    if feed_root and getattr(feed_root, "entries", []):
        for entry in feed_root.entries:
            if "zeepubs" in norm(getattr(entry, "title", "")):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        destino_href = abs_url(BASE_URL, link.href)
                        break
            if destino_href:
                break

    if not destino_href:
        biblios_href = None
        for entry in feed_root.entries:
            if "todas las bibliotecas" in norm(getattr(entry, "title", "")):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        biblios_href = abs_url(BASE_URL, link.href)
                        break
        if biblios_href:
            from opds.helpers import mostrar_feed  # local import to avoid circular
            import feedparser as _fp
            feed_biblios = mostrar_feed(biblios_href, _fp)
            if feed_biblios and getattr(feed_biblios, "entries", []):
                for entry in feed_biblios.entries:
                    if "zeepubs" in norm(getattr(entry, "title", "")):
                        for link in getattr(entry, "links", []):
                            if getattr(link, "rel", "") == "subsection":
                                destino_href = abs_url(BASE_URL, link.href)
                                break
                    if destino_href:
                        break

    if destino_href:
        user_state[uid]["titulo"] = "📁 ZeePubs"
        user_state[uid]["historial"] = []
        user_state[uid]["libros"] = {}
        user_state[uid]["colecciones"] = {}
        user_state[uid]["nav"] = {"prev": None, "next": None}
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
    else:
        await query.answer("No se pudo abrir la biblioteca directamente. Intenta entrar manualmente.", show_alert=False)


async def button_handler(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    ensure_user(uid)

    if data.startswith("col|"):
        idx = int(data.split("|")[1])
        col = user_state[uid]["colecciones"].get(idx)
        if col:
            user_state[uid]["titulo"] = f"📁 {col['titulo']}"
            await mostrar_colecciones(update, context, col["href"], from_collection=True)

    elif data.startswith("lib|"):
        key = data.split("|", 1)[1]
        libro = user_state[uid]["libros"].get(key)
        if libro:
            descarga = str(libro.get("descarga", ""))
            href = str(libro.get("href", ""))
            m = re.search(r'/series/(\d+)/volume/(\d+)/', descarga) or re.search(r'/series/(\d+)/volume/(\d+)/', href)
            if m:
                user_state[uid]["series_id"] = m.group(1)
                user_state[uid]["volume_id"] = m.group(2)
            else:
                m2 = re.search(r'/series/(\d+)', descarga) or re.search(r'/series/(\d+)', href)
                if m2:
                    user_state[uid]["series_id"] = m2.group(1)
                else:
                    logging.warning("DEBUG: No se encontraron IDs en URLs del libro")

            user_state[uid]["ultima_pagina"] = href or descarga

            chat_origen = user_state[uid].get("chat_origen")
            actual_destino = user_state[uid].get("destino") or chat_origen

            menu_prep = None
            if actual_destino == chat_origen:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=query.message.message_id)
                except Exception:
                    logging.debug("No se pudo borrar el mensaje del menú")

                try:
                    prep_msg = await context.bot.send_message(chat_origen, text="⏳ Preparando...")
                    prep_msg_id = getattr(prep_msg, "message_id", None)
                    if prep_msg_id:
                        menu_prep = (chat_origen, prep_msg_id)
                except Exception as e:
                    logging.debug("No se pudo enviar mensaje 'Preparando...': %s", e)
                    menu_prep = None

            await publicar_libro(update, context, uid, libro["titulo"], libro.get("portada", ""), libro.get("descarga", ""), menu_prep=menu_prep)

            if actual_destino != chat_origen:
                try:
                    await query.edit_message_text(f"✅ Publicado: {libro['titulo']}")
                except Exception:
                    logging.debug("Error al editar mensaje de confirmación")

    elif data.startswith("nav|"):
        direction = data.split("|")[1]
        href = user_state[uid]["nav"].get(direction)
        if href:
            await mostrar_colecciones(update, context, href, from_collection=False)
        else:
            await query.answer("No hay más páginas en esa dirección.", show_alert=False)

    elif data == "back":
        if user_state[uid]["historial"]:
            titulo_prev, url_prev = user_state[uid]["historial"].pop()
            user_state[uid]["titulo"] = titulo_prev
            await mostrar_colecciones(update, context, url_prev, from_collection=False)
        else:
            await query.answer("No hay nivel anterior disponible.", show_alert=False)

    elif data == "volver_colecciones":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        root_base = user_state.get(uid, {}).get("opds_root_base", OPDS_ROOT_START)
        user_state[uid]["opds_root"] = root_base
        await mostrar_colecciones(update, context, root_base, from_collection=False)

    elif data == "volver_ultima":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
        ultima_url = user_state[uid].get("ultima_pagina", root_url)
        await mostrar_colecciones(update, context, ultima_url, from_collection=False)

    elif data == "cerrar":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        await query.edit_message_text("👋 ¡Gracias por usar el bot! Hasta la próxima.")


async def volver(update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    if user_state.get(uid, {}).get("historial"):
        titulo_prev, url_prev = user_state[uid]["historial"].pop()
        user_state[uid]["titulo"] = titulo_prev
        await mostrar_colecciones(update, context, url_prev, from_collection=False)
    else:
        await update.message.reply_text("No hay nivel anterior disponible.")