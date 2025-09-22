import asyncio
import logging

from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from config import TELEGRAM_TOKEN
from handlers import (
    start, evil, volver, cancel,
    button_handler, abrir_zeepubs, buscar_epub,
    set_destino, recibir_texto
)
from http.session import get_global_session


async def _close_global_session():
    sess = get_global_session(create_if_missing=False)
    if sess is not None:
        try:
            await sess.close()
        except Exception as e:
            logging.debug("Error closing aiohttp session: %s", e)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Callback handlers
    app.add_handler(CallbackQueryHandler(set_destino, pattern=r"^destino\|"))
    app.add_handler(CallbackQueryHandler(buscar_epub, pattern=r"^buscar$"))
    app.add_handler(CallbackQueryHandler(abrir_zeepubs, pattern=r"^abrir_zeepubs$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("evil", evil))
    app.add_handler(CommandHandler("volver", volver))
    app.add_handler(CommandHandler("cancel", cancel))

    # Messages (text, non commands)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))

    try:
        app.run_polling()
    finally:
        asyncio.run(_close_global_session())


if __name__ == "__main__":
    main()