from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OPDS_ROOT_START
from opds.parser import parse_feed_from_url
from opds.helpers import abs_url
from . import ensure_user, user_state
from .navigation import mostrar_colecciones


def build_search_url(query: str, uid: int | None = None) -> str:
    """
    Reconstruye la URL de búsqueda usando el OPDS root actual del usuario (si existe).
    """
    root = OPDS_ROOT_START
    if uid and uid in user_state:
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)

    if "/series" in root:
        root_series = root.split("?")[0]
    else:
        root_series = f"{root}/series"
    return f"{root_series}?query={query}"


async def buscar_epub(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    ensure_user(uid)
    user_state[uid]["esperando_busqueda"] = True
    await query.edit_message_text("Escribe el título o parte del título del EPUB que quieres buscar:")


async def mostrar_busqueda_resultados(update, context: ContextTypes.DEFAULT_TYPE, uid: int, texto: str, search_url: str):
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