# core/bot.py

import logging
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from telegram.error import TimedOut
from config.config_settings import config
from core.session_manager import session_manager
from handlers.command_handlers import CommandHandlers
from handlers.callback_handlers import (
    set_destino, buscar_epub, abrir_zeepubs, button_handler
)
from handlers.message_handlers import recibir_texto
from plugins.plugin_manager import PluginManager

logger = logging.getLogger(__name__)

async def error_handler(update, context):
    """Manejo global de errores para evitar caídas por timeouts u otros."""
    err = context.error
    if isinstance(err, TimedOut):
        logger.warning("Timeout al procesar update %s: %s", update, err)
        return
    logger.exception("Error en update %s: %s", update, err)
    return

class ZeePubBot:
    """Clase principal del bot."""

    def __init__(self):
        token = config.TELEGRAM_TOKEN
        self.app = ApplicationBuilder().token(token).build()
        self.app.add_error_handler(error_handler)

        # Inicializar plugins
        self.plugin_manager = PluginManager()
        self.plugin_manager.initialize(self.app)

        # Comandos
        self.command_handlers = CommandHandlers(self.app)
        # Los siguientes pueden omitirse si CommandHandlers ya los registra,
        # pero aseguran que estén siempre presentes:
        self.app.add_handler(CommandHandler("start", self.command_handlers.start))
        self.app.add_handler(CommandHandler("help", self.command_handlers.help))
        self.app.add_handler(CommandHandler("status", self.command_handlers.status))
        self.app.add_handler(CommandHandler("cancel", self.command_handlers.cancel))
        self.app.add_handler(CommandHandler("plugins", self.command_handlers.plugins))
        self.app.add_handler(CommandHandler("evil", self.command_handlers.evil))
        # Registrar /search si no está en CommandHandlers
        self.app.add_handler(CommandHandler("search", self.command_handlers.search))
        # Registrar /reset para administradores
        self.app.add_handler(CommandHandler("reset", self.command_handlers.reset_command))

        # Callbacks
        self.app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino"))
        self.app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar"))
        self.app.add_handler(CallbackQueryHandler(abrir_zeepubs, pattern="^abrir"))
        self.app.add_handler(CallbackQueryHandler(button_handler))

        # Mensajes de texto
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))

    def start(self):
        """Arranca el bot en polling."""
        logger.info("Bot iniciado, entrando en polling...")
        self.app.run_polling()
        session_manager.close()
