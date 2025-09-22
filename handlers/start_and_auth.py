import hashlib
import datetime
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import SECRET_SEED, OPDS_ROOT_START, OPDS_ROOT_EVIL
from . import ensure_user, user_state
from .navigation import mostrar_colecciones
from .search import build_search_url, mostrar_busqueda_resultados


def get_six_hour_password() -> str:
    now = datetime.datetime.now()
    bloque = now.hour // 6
    raw = f"{SECRET_SEED}{now.year}-{now.month}-{now.day}-B{bloque}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


async def start(update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_START
    ensure_user(uid)
    user_state[uid].update({
        "titulo": "📚 Todas las bibliotecas",
        "destino": update.effective_chat.id,
        "chat_origen": update.effective_chat.id,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url,
        "auto_enter_done": False
    })
    await mostrar_colecciones(update, context, root_url, from_collection=False)


async def evil(update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_EVIL
    ensure_user(uid)
    user_state[uid].update({
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": update.effective_chat.id,
        "esperando_password": True,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url
    })
    await update.message.reply_text("🔒 Ingresa la contraseña para acceder a este modo:")


async def cancel(update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cancel - Restablece el estado del usuario y cierra mensajes temporales.
    """
    uid = update.effective_user.id
    ensure_user(uid)

    msg_id = user_state[uid].pop("msg_que_hacer", None)
    chat_id = None
    try:
        chat_id = update.effective_chat.id
    except Exception:
        chat_id = None

    if msg_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            logging.debug("cancel: no se pudo borrar msg_que_hacer (chat=%s msg=%s)", chat_id, msg_id)

    menu_prep = user_state[uid].pop("menu_prep", None)
    if menu_prep and isinstance(menu_prep, tuple):
        try:
            _chat, _msg = menu_prep
            if _chat and _msg:
                await context.bot.delete_message(chat_id=_chat, message_id=_msg)
        except Exception:
            logging.debug("cancel: no se pudo borrar menu_prep %r", menu_prep)

    user_state[uid].update({
        "historial": [],
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None},
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": None,
        "esperando_destino_manual": False,
        "esperando_busqueda": False,
        "esperando_password": False,
        "ultima_pagina": None,
        "opds_root": OPDS_ROOT_START,
        "opds_root_base": OPDS_ROOT_START,
        "series_id": None,
        "volume_id": None,
        "msg_que_hacer": None
    })

    try:
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text="✅ Operación cancelada. El bot está listo. Usa /start para comenzar.")
        else:
            if getattr(update, "message", None):
                await update.message.reply_text("✅ Operación cancelada. El bot está listo. Usa /start para comenzar.")
    except Exception:
        logging.debug("cancel: no se pudo enviar mensaje de confirmación")


async def recibir_texto(update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja textos:
    - contraseña para modo evil
    - destino manual
    - texto de búsqueda (delegado a search)
    """
    uid = update.effective_user.id
    ensure_user(uid)
    texto = update.message.text.strip()

    # Password flow
    if user_state.get(uid, {}).get("esperando_password"):
        if texto == get_six_hour_password():
            user_state[uid]["esperando_password"] = False
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
            user_state[uid]["esperando_password"] = False
            await update.message.reply_text("❌ Contraseña incorrecta. Volviendo al modo normal…")
            await start(update, context)
        return

    # Destino manual
    if user_state.get(uid, {}).get("esperando_destino_manual"):
        user_state[uid]["destino"] = texto
        user_state[uid]["esperando_destino_manual"] = False
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]" if root == OPDS_ROOT_EVIL else "📚 Todas las bibliotecas"
        await mostrar_colecciones(update, context, root, from_collection=False)
        return

    # Búsqueda (delegado)
    if user_state.get(uid, {}).get("esperando_busqueda"):
        user_state[uid]["esperando_busqueda"] = False
        search_url = build_search_url(texto, uid)
        await mostrar_busqueda_resultados(update, context, uid, texto, search_url)
        return