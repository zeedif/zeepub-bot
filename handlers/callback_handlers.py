# handlers/callback_handlers.py
import re
import os
import uuid
import logging
from urllib.parse import urlparse, unquote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config.config_settings import config
from core.state_manager import state_manager
from services.opds_service import mostrar_colecciones, buscar_zeepubs_directo
from services.telegram_service import publicar_libro
from utils.helpers import build_search_url
from utils.helpers import find_zeepubs_destino
from utils.http_client import parse_feed_from_url
from services.opds_service import mostrar_colecciones


logger = logging.getLogger(__name__)

async def set_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle destination selection"""
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    _, destino = query.data.split("|", 1)
    
    if destino == "aqui":
        # Publish in current chat
        state_manager.update_user_state(uid, {"destino": update.effective_chat.id})
        
        user_state = state_manager.get_user_state(uid)
        root = user_state.get("opds_root", config.OPDS_ROOT_START)
        
        # Update title based on root
        if root == config.OPDS_ROOT_EVIL:
            state_manager.update_user_state(uid, {"titulo": "📁 ZeePubs [ES]"})
        else:
            state_manager.update_user_state(uid, {"titulo": "📚 Todas las bibliotecas"})
        
        await mostrar_colecciones(update, context, root, from_collection=False)
        
    elif destino in ["@ZeePubBotTest", "@ZeePubs"]:
        # Remote destination
        state_manager.update_user_state(uid, {"destino": destino})
        
        user_state = state_manager.get_user_state(uid)
        root = user_state.get("opds_root", config.OPDS_ROOT_START)
        
        if root == config.OPDS_ROOT_EVIL:
            state_manager.update_user_state(uid, {"titulo": "📁 ZeePubs [ES]"})
        else:
            state_manager.update_user_state(uid, {"titulo": "📚 Todas las bibliotecas"})
        
        await mostrar_colecciones(update, context, root, from_collection=False)
        
    elif destino == "otro":
        state_manager.update_user_state(uid, {"esperando_destino_manual": True})
        await query.edit_message_text("Escribe el @usuario o chat_id donde quieres publicar:")

async def buscar_epub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search button"""
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    
    state_manager.update_user_state(uid, {"esperando_busqueda": True})
    await query.edit_message_text("Escribe el título o parte del título del EPUB que quieres buscar:")

async def abrir_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct ZeePubs access"""
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    
    await buscar_zeepubs_directo(update, context, uid)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    user_state = state_manager.get_user_state(uid)
    
    if data.startswith("col|"):
        idx = int(data.split("|")[1])
        col = user_state["colecciones"].get(idx)
        if col:
            titulo = col["titulo"]
            if titulo.strip().lower() == "todas las bibliotecas":
                # Solo para modo start (raíz pública) hacer salto directo a ZeePubs [ES]
                if user_state.get("opds_root_base") == config.OPDS_ROOT_START:
                    feed_root = await parse_feed_from_url(col["href"])
                    destino_zeepubs = find_zeepubs_destino(feed_root, prefer_libraries=True)
                    if destino_zeepubs:
                        user_state["opds_root"] = destino_zeepubs
                        user_state["titulo"] = "📁 ZeePubs [ES]"
                        await mostrar_colecciones(update, context, destino_zeepubs, from_collection=True)
                        return
            state_manager.update_user_state(uid, {"titulo": f"📁 {titulo}"})
            await mostrar_colecciones(update, context, col["href"], from_collection=True)
    
    elif data.startswith("lib|"):
        # Book selection
        key = data.split("|", 1)[1]
        libro = user_state["libros"].get(key)
        if libro:
            descarga = str(libro.get("descarga", ""))
            href = str(libro.get("href", ""))
            
            # Extract series and volume IDs
            m = re.search(r'/series/(\d+)/volume/(\d+)/', descarga) or re.search(r'/series/(\d+)/volume/(\d+)/', href)
            if m:
                state_manager.update_user_state(uid, {
                    "series_id": m.group(1),
                    "volume_id": m.group(2)
                })
                logger.info(f"DEBUG series_id: {m.group(1)} volume_id: {m.group(2)}")
            else:
                m2 = re.search(r'/series/(\d+)', descarga) or re.search(r'/series/(\d+)', href)
                if m2:
                    state_manager.update_user_state(uid, {"series_id": m2.group(1)})
                    logger.info(f"DEBUG series_id: {m2.group(1)}")
                else:
                    logger.warning("DEBUG: No se encontraron IDs en URLs del libro")
            
            state_manager.update_user_state(uid, {"ultima_pagina": href or descarga})
            
            # Determine actual destination
            chat_origen = user_state.get("chat_origen")
            actual_destino = user_state.get("destino") or chat_origen
            
            # If publishing in same chat, delete menu and show temp message
            menu_prep = None
            if actual_destino == chat_origen:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id, 
                        message_id=query.message.message_id
                    )
                except Exception:
                    logger.debug("No se pudo borrar el mensaje del menú")
                
                try:
                    prep_msg = await context.bot.send_message(chat_origen, text="⏳ Preparando...")
                    prep_msg_id = getattr(prep_msg, "message_id", None)
                    if prep_msg_id:
                        menu_prep = (chat_origen, prep_msg_id)
                except Exception as e:
                    logger.debug(f"No se pudo enviar mensaje 'Preparando...': {e}")
            
            # Publish the book
            await publicar_libro(
                update, context, uid, libro["titulo"], 
                libro.get("portada", ""), libro.get("descarga", ""), 
                menu_prep=menu_prep
            )
            
            # If publishing elsewhere, edit original menu
            if actual_destino != chat_origen:
                try:
                    await query.edit_message_text(f"✅ Publicado: {libro['titulo']}")
                except Exception:
                    logger.debug("Error al editar mensaje de confirmación")
    
    elif data.startswith("nav|"):
        # Navigation
        direction = data.split("|")[1]
        href = user_state["nav"].get(direction)
        if href:
            await mostrar_colecciones(update, context, href, from_collection=False)
        else:
            await query.answer("No hay más páginas en esa dirección.", show_alert=False)
    
    elif data == "back":
        # Go back
        if user_state["historial"]:
            titulo_prev, url_prev = user_state["historial"].pop()
            state_manager.update_user_state(uid, {"titulo": titulo_prev})
            await mostrar_colecciones(update, context, url_prev, from_collection=False)
        else:
            await query.answer("No hay nivel anterior disponible.", show_alert=False)
    
    elif data == "volver_colecciones":
        # Return to collections
        msg_id = user_state.pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, 
                    message_id=msg_id
                )
            except Exception:
                pass
        
        root_base = user_state.get("opds_root_base", config.OPDS_ROOT_START)
        state_manager.update_user_state(uid, {"opds_root": root_base})
        await mostrar_colecciones(update, context, root_base, from_collection=False)
    
    elif data == "volver_ultima":
        # Return to last page
        msg_id = user_state.pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, 
                    message_id=msg_id
                )
            except Exception:
                pass
        
        root_url = user_state.get("opds_root", config.OPDS_ROOT_START)
        ultima_url = user_state.get("ultima_pagina", root_url)
        await mostrar_colecciones(update, context, ultima_url, from_collection=False)
    
    elif data == "cerrar":
        # Close
        msg_id = user_state.pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, 
                    message_id=msg_id
                )
            except Exception:
                pass
        await query.edit_message_text("👋 ¡Gracias por usar el bot! Hasta la próxima.")