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
from config.config_settings import config
from utils.helpers import find_zeepubs_destino
from utils.http_client import parse_feed_from_url

logger = logging.getLogger(__name__)

async def set_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    uid = update.effective_user.id
    _, destino = query.data.split("|", 1)
    st = state_manager.get_user_state(uid)

    # Destinos preconfigurados o "aqui"
    if destino == "aqui" or destino in ("@ZeePubBotTest", "@ZeePubs"):
        st["destino"] = update.effective_chat.id if destino == "aqui" else destino
        st["titulo"] = "📚 Categorías"
        await query.answer("✅ Destino seleccionado")
        
        # Si no es admin, ir directamente a ZeePubs [ES]
        if uid not in config.ADMIN_USERS:
            await buscar_zeepubs_directo(update, context, uid)
        else:
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
    try:
        await query.answer()
    except Exception:
        pass
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    chat = update.effective_chat
    
    # En chats privados, siempre usar texto libre
    if chat.type == 'private':
        st["esperando_busqueda"] = True
        await query.edit_message_text("🔍 Escribe parte del título del EPUB:")
        return
    
    # En grupos, verificar si el bot es administrador
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_admin = bot_member.status in ['administrator', 'creator']
    except Exception:
        is_admin = False
    
    if is_admin:
        # Bot es admin: puede recibir mensajes normales
        st["esperando_busqueda"] = True
        await query.edit_message_text("🔍 Escribe parte del título del EPUB:")
    else:
        # Bot NO es admin: solo recibe comandos
        await query.edit_message_text(
            "🔍 Para buscar, usa el comando:\n\n"
            "<code>/search término de búsqueda</code>\n\n"
            "Ejemplo: <code>/search harry potter</code>",
            parse_mode="HTML"
        )


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
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)

    # Selección de colección
    if data.startswith("col|"):
        idx = int(data.split("|", 1)[1])
        col = st["colecciones"].get(idx)
        if col:
            titulo_col = col.get("titulo", "").lower()
            
            # Si no es admin y es "Todas las bibliotecas", saltar a ZeePubs [ES] directamente
            if uid not in config.ADMIN_USERS and "todas las bibliotecas" in titulo_col:
                from services.opds_service import get_zeepubs_first_library
                
                root_page = {
                    "titulo": "📚 Todas las bibliotecas",
                    "url": st.get("opds_root"),
                    "type": "root"
                }
                st["historial"] = [root_page]
                st["titulo"] = "📁 Biblioteca ZeePubs"
                
                zeepubs_first_url = await get_zeepubs_first_library(st.get("opds_root"))
                await mostrar_colecciones(update, context, zeepubs_first_url, from_collection=True)
            else:
                # Navegar normalmente a la colección (para admins o colecciones que no sean "Todas las bibliotecas")
                current_page = {
                    "titulo": st.get("titulo", ""),
                    "url": st.get("url", ""),
                    "type": "collection"
                }
                if "historial" not in st:
                    st["historial"] = []
                st["historial"].append(current_page)
                
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
                from utils.helpers import get_thread_id
                thread_id = st.get("message_thread_id")  # Usar el guardado
                
                prep = await context.bot.send_message(
                    chat_id=chat_origen,
                    text="⏳ Preparando...",
                    message_thread_id=thread_id
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

    # Publisher flow: publish target selection
    if data.startswith("publish_target|"):
        choice = data.split("|", 1)[1]
        uid = update.effective_user.id
        if choice == "facebook":
            from services.telegram_service import _publish_choice_facebook
            await _publish_choice_facebook(update, context, uid)
        else:
            from services.telegram_service import _publish_choice_telegram
            await _publish_choice_telegram(update, context, uid)
        try:
            await query.answer()
        except Exception as e:
            logger.debug("Could not answer publish_target callback: %s", e)
        return

    # Subir nivel (usar historial para ir al nivel anterior)
    if data == "subir_nivel":
        if "historial" not in st:
            st["historial"] = []
        
        if st["historial"]:
            last_page = st["historial"].pop()
            if last_page and last_page.get("url"):
                st["titulo"] = last_page["titulo"]
                st["url"] = last_page["url"]
                await mostrar_colecciones(update, context, last_page["url"], from_collection=True)
            else:
                root = st.get("opds_root_base") or st.get("opds_root")
                st["titulo"] = "📚 Categorías"
                st["url"] = root
                await mostrar_colecciones(update, context, root, from_collection=False)
        else:
            root = st.get("opds_root_base") or st.get("opds_root")
            st["titulo"] = "📚 Categorías"
            st["url"] = root
            await mostrar_colecciones(update, context, root, from_collection=False)
        return

    # Navegación paginada (solo dentro de la misma página, sin historial)
    if data.startswith("nav|"):
        direction = data.split("|", 1)[1]
        nav_url = st.get("nav", {}).get(direction)
        if nav_url:
            st["url"] = nav_url
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

    # Volver a última página donde se listaban los EPUB
    if data == "volver_ultima":
        # Borrar mensaje de botones (el actual)
        try:
            await query.message.delete()
        except Exception:
            pass

        last_url = st.get("ultima_pagina")
        if last_url:
            # Opcional: Si también guardas el título anterior, úsalo aquí
            st["titulo"] = "📚 Última página"
            st["url"] = last_url
            # Usar new_message=True para que no borre el mensaje del libro
            await mostrar_colecciones(update, context, last_url, from_collection=True, new_message=True)
        else:
            # Si no hay última página guardada, usar historial como antes
            if "historial" not in st:
                st["historial"] = []
            if st["historial"]:
                last_page = st["historial"].pop()
                if last_page and last_page.get("url"):
                    st["titulo"] = last_page["titulo"]
                    st["url"] = last_page["url"]
                    await mostrar_colecciones(update, context, last_page["url"], from_collection=True, new_message=True)
                else:
                    root = st.get("opds_root_base") or st.get("opds_root")
                    st["titulo"] = "📚 Categorías"
                    st["url"] = root
                    await mostrar_colecciones(update, context, root, from_collection=False, new_message=True)
            else:
                root = st.get("opds_root_base") or st.get("opds_root")
                st["titulo"] = "📚 Categorías"
                st["url"] = root
                await mostrar_colecciones(update, context, root, from_collection=False, new_message=True)
        return

    # Cerrar menú
    if data == "cerrar":
        await query.edit_message_text("👋 Gracias por usar el bot.")
        return

    # Descargar EPUB pendiente
    if data == "descargar_epub":
        try:
            await query.answer()
        except Exception as e:
            logger.debug("Could not answer callback for descargar_epub: %s", e)
        from services.telegram_service import descargar_epub_pendiente
        await descargar_epub_pendiente(update, context, uid)
        return

    # Facebook handlers
    if data == "preparar_post_fb":
        from services.telegram_service import preparar_post_facebook
        await preparar_post_facebook(update, context, uid)
        try:
            await query.answer()
        except Exception as e:
            logger.debug("Could not answer callback for preparar_post_fb: %s", e)
        return

    if data == "publicar_fb":
        from services.telegram_service import publicar_facebook_action
        await publicar_facebook_action(update, context, uid)
        try:
            await query.answer()
        except Exception as e:
            logger.debug("Could not answer callback for publicar_fb: %s", e)
        return

    if data == "descartar_fb":
        try:
            await query.message.delete()
            await query.answer("🗑️ Descartado")
        except Exception as e:
            logger.debug("Could not discard FB preview/delete message: %s", e)
        return

def register_handlers(app):
    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino\\|"))
    app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar$"))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(col\\||lib\\||nav\\||subir_nivel|volver_colecciones|volver_ultima|cerrar|descargar_epub|preparar_post_fb|publicar_fb|descartar_fb)"))
    # Texto libre handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_destino))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
