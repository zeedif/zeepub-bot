import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import time
from config.config_settings import config
from core.state_manager import state_manager
from services.opds_service import mostrar_colecciones
from utils.download_limiter import downloads_left, DOWNLOAD_WHITELIST

logger = logging.getLogger(__name__)

MAX_DOWNLOADS_PER_HOUR = getattr(config, "MAX_DOWNLOADS_PER_HOUR", 5)
DOWNLOAD_TIME_WINDOW = 3600  # segundos en una hora

user_download_limits = {}


def downloads_left(user_id):
    if user_id in DOWNLOAD_WHITELIST:
        return "ilimitadas"
    now = time.time()
    timestamps = user_download_limits.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < DOWNLOAD_TIME_WINDOW]
    return MAX_DOWNLOADS_PER_HOUR - len(timestamps)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    uid = update.effective_user.id
    root_url = config.OPDS_ROOT_START

    # Mostrar descargas restantes
    left = downloads_left(uid)
    if left == "ilimitadas":
        texto = "Tienes descargas ilimitadas."
    else:
        texto = f"⚡️ Te quedan {left} descargas de EPUB en esta hora."
    await update.message.reply_text(texto)

    # Initialize user state for public root
    state_manager.update_user_state(uid, {
        "titulo": "📚 Todas las bibliotecas",
        "destino": update.effective_chat.id,
        "chat_origen": update.effective_chat.id,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url,
        "auto_enter_done": False
    })

    # Show root menu (no auto-enter)
    await mostrar_colecciones(update, context, root_url, from_collection=False)


async def evil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /evil command - requires password"""
    uid = update.effective_user.id
    root_url = config.OPDS_ROOT_EVIL

    state_manager.update_user_state(uid, {
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": update.effective_chat.id,
        "esperando_password": True,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url
    })

    await update.message.reply_text("🔒 Ingresa la contraseña para acceder a este modo:")


async def volver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /volver command"""
    uid = update.effective_user.id
    user_state = state_manager.get_user_state(uid)

    if user_state.get("historial"):
        titulo_prev, url_prev = user_state["historial"].pop()
        state_manager.update_user_state(uid, {"titulo": titulo_prev})
        await mostrar_colecciones(update, context, url_prev, from_collection=False)
    else:
        await update.message.reply_text("No hay nivel anterior disponible.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command"""
    uid = update.effective_user.id
    user_state = state_manager.get_user_state(uid)

    # Try to delete last menu message
    msg_id = user_state.pop("msg_que_hacer", None)
    chat_id = None

    try:
        chat_id = update.effective_chat.id
    except Exception:
        chat_id = None

    if msg_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            logger.debug(f"cancel: no se pudo borrar msg_que_hacer (chat={chat_id} msg={msg_id})")

    # Clean up menu_prep if exists
    menu_prep = user_state.pop("menu_prep", None)
    if menu_prep and isinstance(menu_prep, tuple):
        try:
            _chat, _msg = menu_prep
            if _chat and _msg:
                await context.bot.delete_message(chat_id=_chat, message_id=_msg)
        except Exception:
            logger.debug(f"cancel: no se pudo borrar menu_prep {menu_prep!r}")

    # Reset user state
    state_manager.reset_user_state(uid)

    # Send confirmation
    try:
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Operación cancelada. El bot está listo. Usa /start para comenzar."
            )
        else:
            if getattr(update, "message", None):
                await update.message.reply_text(
                    "✅ Operación cancelada. El bot está listo. Usa /start para comenzar."
                )
    except Exception:
        logger.debug("cancel: no se pudo enviar mensaje de confirmación")
