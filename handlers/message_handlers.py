# handlers/message_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config.config_settings import config
from core.state_manager import state_manager
from services.opds_service import mostrar_colecciones, parse_feed_from_url
from utils.helpers import build_search_url

logger = logging.getLogger(__name__)

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    uid = update.effective_user.id
    user_state = state_manager.get_user_state(uid)
    texto = update.message.text.strip()
    
    # Handle password input
    if user_state.get("esperando_password"):
        if texto == config.get_six_hour_password():
            state_manager.update_user_state(uid, {"esperando_password": False})
            keyboard = [
                [InlineKeyboardButton("📍 Publicar aquí", callback_data="destino|aqui")],
                [InlineKeyboardButton("📢 ZeePubBotTest", callback_data="destino|@ZeePubBotTest")],
                [InlineKeyboardButton("📢 ZeePubs", callback_data="destino|@ZeePubs")],
                [InlineKeyboardButton("✏️ Otro destino", callback_data="destino|otro")]
            ]
            await update.message.reply_text(
                "✅ Contraseña correcta. ¿Dónde quieres publicar los libros?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            state_manager.update_user_state(uid, {"esperando_password": False})
            await update.message.reply_text("❌ Contraseña incorrecta. Volviendo al modo normal…")
            # Import here to avoid circular import
            from handlers.command_handlers import start
            await start(update, context)
        return
    
    # Handle manual destination input
    if user_state.get("esperando_destino_manual"):
        state_manager.update_user_state(uid, {
            "destino": texto,
            "esperando_destino_manual": False
        })
        
        # Use current OPDS root
        root = user_state.get("opds_root", config.OPDS_ROOT_START)
        
        # Update title based on root
        if root == config.OPDS_ROOT_EVIL:
            state_manager.update_user_state(uid, {"titulo": "📁 ZeePubs [ES]"})
        else:
            state_manager.update_user_state(uid, {"titulo": "📚 Todas las bibliotecas"})
        
        # Show collections immediately
        await mostrar_colecciones(update, context, root, from_collection=False)
    
    # Handle search input
    elif user_state.get("esperando_busqueda"):
        state_manager.update_user_state(uid, {"esperando_busqueda": False})
        search_url = build_search_url(texto, uid)
        
        feed = await parse_feed_from_url(search_url)
        if not feed or not getattr(feed, "entries", []):
            keyboard = [
                [InlineKeyboardButton("🔄 Volver a buscar", callback_data="buscar")],
                [InlineKeyboardButton("📚 Ir a colecciones", callback_data="volver_colecciones")]
            ]
            await update.message.reply_text(
                f"🔍 No se encontraron resultados para: {texto}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await mostrar_colecciones(update, context, search_url, from_collection=False)