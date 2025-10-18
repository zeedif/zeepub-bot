# handlers/callback_handlers.py

import re
import uuid
import logging
from urllib.parse import unquote, urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from core.state_manager import state_manager
from services.opds_service import mostrar_colecciones, buscar_zeepubs_directo
from services.telegram_service import publicar_libro

logger = logging.getLogger(__name__)

async def set_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    _, destino = query.data.split("|", 1)
    st = state_manager.get_user_state(uid)

    # Destinos preconfigurados o "aqui"
    if destino == "aqui" or destino in ("@ZeePubBotTest", "@ZeePubs"):
        st["destino"] = update.effective_chat.id if destino == "aqui" else destino
        st["titulo"] = "📚 Categorías"
        await query.answer("✅ Destino seleccionado")
        await mostrar_colecciones(update, context, st["opds_root"], from_collection=False)
        return

    # Destino manual
    if destino == "otro":
        st["esperando_destino_manual"] = True
        await query.edit_message_text("✏️ Escribe @usuario o chat_id para publicar:")
        return

async def handle_manual_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura texto tras elegir 'Otro' para destino manual."""
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    if not st.get("esperando_destino_manual"):
        return

    destino_text = update.message.text.strip()
    st["destino"] = destino_text
    st.pop("esperando_destino_manual", None)
    st["titulo"] = "📚 Categorías"
    # Mostrar colecciones Evil con el nuevo destino
    await mostrar_colecciones(update, context, st["opds_root"], from_collection=False)

async def buscar_epub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    st["esperando_busqueda"] = True
    await query.edit_message_text("🔍 Escribe parte del título del EPUB:")

async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura texto tras /search o tras inline 'Buscar EPUB'."""
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    if not st.get("esperando_busqueda"):
        return

    termino = update.message.text.strip()
    st.pop("esperando_busqueda", None)
    # Lanza búsqueda y muestra resultados
    await buscar_zeepubs_directo(update, context, uid, termino)

async def abrir_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await buscar_zeepubs_directo(update, context, update.effective_user.id)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)

    # Selección de colección
    if data.startswith("col|"):
        idx = int(data.split("|", 1)[1])
        col = st["colecciones"].get(idx)
        if col:
            st["historial"].append((st.get("titulo", ""), st.get("url", "")))
            st["titulo"] = f"📁 {col['titulo']}"
            st["url"] = col["href"]
            await mostrar_colecciones(update, context, col["href"], from_collection=True)
        return

    # Selección de libro
    if data.startswith("lib|"):
        key = data.split("|", 1)[1]
        libro = st["libros"].get(key)
        if not libro:
            return

        href = libro.get("descarga") or libro.get("href")
        m = re.search(r"/series/(\d+)/volume/(\d+)/", href)
        if m:
            st["series_id"], st["volume_id"] = m.group(1), m.group(2)
        st["ultima_pagina"] = st.get("url")

        # Preparar menú y mensaje "Preparando..."
        actual_destino = st.get("destino") or update.effective_chat.id
        chat_origen = st.get("chat_origen") or update.effective_chat.id
        menu_prep = None
        if actual_destino == chat_origen:
            try:
                await context.bot.delete_message(
                    chat_id=chat_origen,
                    message_id=query.message.message_id
                )
            except Exception:
                logger.debug("No se pudo borrar menú")
            try:
                prep = await context.bot.send_message(
                    chat_id=chat_origen,
                    text="⏳ Preparando..."
                )
                menu_prep = (chat_origen, prep.message_id)
            except Exception as e:
                logger.debug("No se pudo enviar 'Preparando...': %s", e)

        # Publicar EPUB
        await publicar_libro(
            update, context, uid,
            libro["titulo"],
            libro.get("portada", ""),
            href,
            menu_prep=menu_prep
        )

        # Confirmación si es otro destino
        if actual_destino != chat_origen:
            try:
                await query.edit_message_text(f"✅ Publicado: {libro['titulo']}")
            except Exception:
                logger.debug("Error al editar confirmación")
        return

    # Navegación paginada
    if data.startswith("nav|"):
        direction = data.split("|", 1)[1]
        nav_url = st.get("nav", {}).get(direction)
        if nav_url:
            await mostrar_colecciones(update, context, nav_url, from_collection=False)
        else:
            await query.answer("🚫 No hay más páginas")
        return

    # Volver a categorías raíz
    if data == "volver_colecciones":
        root = st.get("opds_root_base") or st.get("opds_root")
        st["historial"] = []
        st["titulo"] = "📚 Categorías"
        st["url"] = root
        await mostrar_colecciones(update, context, root, from_collection=False)
        return

    # Volver a última página
    if data == "volver_ultima":
        last = st.get("ultima_pagina")
        if last:
            await mostrar_colecciones(update, context, last, from_collection=False)
        else:
            await query.answer("🚫 No hay página anterior")
        return

    # Cerrar menú
    if data == "cerrar":
        await query.edit_message_text("👋 Gracias por usar el bot.")
        return

    # Descargar EPUB pendiente
    if data == "descargar_epub":
        await query.answer()
        from services.telegram_service import descargar_epub_pendiente
        await descargar_epub_pendiente(update, context, uid)
        return

def register_handlers(app):
    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino\\|"))
    app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar$"))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(col\\||lib\\||nav\\||volver_colecciones|volver_ultima|cerrar)"))
    # Texto libre handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_destino))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
