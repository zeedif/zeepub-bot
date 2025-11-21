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


async def mostrar_colecciones(update, context: ContextTypes.DEFAULT_TYPE, url: str, from_collection: bool = False, new_message: bool = False):
    """Mostrar colecciones o libros basados en un feed OPDS."""
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    
    # Inicializar historial si no existe
    if "historial" not in st:
        st["historial"] = []
    
    feed = await parse_feed_from_url(url)
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if hasattr(update, "message") and update.message:
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return

    root_url = st.get("opds_root")
    
    # Actualizar estado (sin tocar historial, lo gestiona el handler)
    st.update({
        "url": url,
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None}
    })

    # enlaces de navegación (paginación dentro de la misma biblioteca)
    logger.debug(f"Total links en feed: {len(getattr(feed.feed, 'links', []))}")
    for link in getattr(feed.feed, 'links', []):
        rel = getattr(link, "rel", "")
        href = abs_url(config.BASE_URL, link.href)
        logger.debug(f"Link encontrado - rel: {rel}, href: {href}")
        if rel == "prev" or rel == "previous":  # Añade "prev"
            st["nav"]["prev"] = href
        elif rel == "next":
            st["nav"]["next"] = href
    
    logger.debug(f"Final nav state - prev: {st['nav']['prev']}, next: {st['nav']['next']}")
    
    # NO sobrescribas el prev del feed con el historial
    # El historial se usa solo para "Subir nivel", no para paginación

    colecciones, libros = [], []
    ocultos = {"En el puente", "Listas de lectura", "Deseo leer", "Todas las colecciones"}
    
    # No ocultar "Todas las bibliotecas" para admins, pero sí procesarla diferente para no-admins
    
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
            titulo_boton = col["titulo"]
            
            # Para no-admins, mostrar "Biblioteca ZeePubs" en lugar de "Todas las bibliotecas"
            if uid not in config.ADMIN_USERS and col["titulo"] == "Todas las bibliotecas":
                titulo_boton = "📚 Biblioteca ZeePubs"
            
            keyboard.append([InlineKeyboardButton(titulo_boton, callback_data=f"col|{i}")])
    else:
        for b in libros:
            key = uuid.uuid4().hex[:8]
            st["libros"][key] = b
            name = unquote(urlparse(b["descarga"]).path.split("/")[-1]).replace(".epub", "")
            keyboard.append([InlineKeyboardButton(name, callback_data=f"lib|{key}")])

    # Botones de navegación: todos en la misma fila
    nav_buttons = []
    
    # Botón "Subir nivel" (usar historial para ir al nivel anterior)
    if st["historial"]:
        nav_buttons.append(InlineKeyboardButton("⬆️ Subir nivel", callback_data="subir_nivel"))
    
    # Botones de paginación (navegar dentro de la misma biblioteca)
    if st["nav"]["prev"]:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data="nav|prev"))
    if st["nav"]["next"]:
        nav_buttons.append(InlineKeyboardButton("➡️ Siguiente", callback_data="nav|next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Botón Salir solo en el primer nivel (sin historial)
    if not st["historial"]:
        keyboard.append([InlineKeyboardButton("❌ Salir", callback_data="cerrar")])

    # Título y markup
    title = st.get("titulo") or "📚 Categorías"
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Enviar o editar mensaje
    if new_message:
         # Si se pide mensaje nuevo, usar reply_text (o send_message)
         # Se asume que update tiene message o callback_query.message
         from utils.helpers import get_thread_id
         thread_id = get_thread_id(update)
         chat_id = update.effective_chat.id
         await context.bot.send_message(
             chat_id=chat_id, 
             text=title, 
             reply_markup=reply_markup,
             message_thread_id=thread_id
         )
    elif hasattr(update, "message") and update.message:
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

async def get_zeepubs_first_library(url: str) -> str:
    """Obtiene la URL de la primera biblioteca dentro de ZeePubs [ES]."""
    # url es la raíz (OPDS_ROOT)
    feed = await parse_feed_from_url(url)
    libraries_url = find_zeepubs_destino(feed, prefer_libraries=True)
    
    # Ahora obtener la primera biblioteca dentro de /libraries
    lib_feed = await parse_feed_from_url(libraries_url)
    for entry in lib_feed.entries:
        for link in getattr(entry, "links", []):
            if getattr(link, "rel", "") == "subsection":
                return abs_url(config.BASE_URL, link.href)
    
    return libraries_url
