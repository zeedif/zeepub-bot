# handlers/message_handlers.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import state_manager
from services.opds_service import mostrar_colecciones
from config.config_settings import config
from utils.helpers import build_search_url
from utils.http_client import parse_feed_from_url

logger = logging.getLogger(__name__)

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto cuando se espera input del usuario."""
    uid = update.effective_user.id
    st = state_manager.get_user_state(uid)
    text = update.message.text.strip()

    # 1) Contraseña para modo 'evil'
    if st.get("esperando_password"):
        st["esperando_password"] = False
        if text == config.get_six_hour_password():
            keyboard = [
                [InlineKeyboardButton("📍 Aquí", callback_data="destino|aqui")],
                [InlineKeyboardButton("📢 BotTest", callback_data="destino|@ZeePubBotTest")],
                [InlineKeyboardButton("📢 ZeePubs", callback_data="destino|@ZeePubs")],
                [InlineKeyboardButton("✏️ Otro", callback_data="destino|otro")],
            ]
            # Editar el prompt original si se guardó
            msg_id = st.get("msg_esperando_pwd")
            if msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=msg_id,
                        text="✅ Contraseña correcta. Elige destino:",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                except Exception:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ Contraseña correcta. Elige destino:",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="✅ Contraseña correcta. Elige destino:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Contraseña incorrecta."
            )
        return

    # 2) Destino manual
    if st.get("esperando_destino_manual"):
        st["esperando_destino_manual"] = False
        st["destino"] = text
        await mostrar_colecciones(update, context, st["opds_root"], from_collection=False)
        return

    # 3) Búsqueda de EPUB
    if st.get("esperando_busqueda"):
        st["esperando_busqueda"] = False
        search_url = build_search_url(text, uid)
        feed = await parse_feed_from_url(search_url)
        if not feed or not getattr(feed, "entries", []):
            keyboard = [
                [InlineKeyboardButton("🔄 Volver a buscar", callback_data="buscar")],
                [InlineKeyboardButton("📚 Ir a colecciones", callback_data="volver_colecciones")],
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🔍 No se encontraron resultados para: {text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await mostrar_colecciones(update, context, search_url, from_collection=False)
        return

    # 4) Cualquier otro texto
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Usa /start para comenzar o selecciona una opción del menú."
    )
