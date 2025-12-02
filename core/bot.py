# core/bot.py

import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TimedOut
from config.config_settings import config
from core.session_manager import session_manager
from handlers.command_handlers import CommandHandlers
from handlers.callback_handlers import (
    set_destino,
    buscar_epub,
    abrir_zeepubs,
    button_handler,
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

        # Inicializar plugins manager (async init happens in initialize())
        self.plugin_manager = PluginManager()
        # attach plugin manager to app so handlers can access it
        setattr(self.app, "plugin_manager", self.plugin_manager)

        # Comandos
        self.command_handlers = CommandHandlers(self.app)
        # Handlers are registered in CommandHandlers.__init__

        # Callbacks
        self.app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino"))
        self.app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar"))
        self.app.add_handler(CallbackQueryHandler(abrir_zeepubs, pattern="^abrir"))
        self.app.add_handler(CallbackQueryHandler(button_handler))

        # Mini App handlers
        from handlers.webapp_handlers import (
            register_handlers as register_webapp_handlers,
        )

        register_webapp_handlers(self.app)

        # Mensajes de texto
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto)
        )

        # JSON Upload Handler
        from handlers.message_handlers import handle_json_upload
        self.app.add_handler(
            MessageHandler(filters.Document.MimeType("application/json"), handle_json_upload)
        )

    def start(self):
        """Arranca el bot en polling (bloqueante, modo legacy)."""
        logger.info("Bot iniciado, entrando en polling...")
        self.app.run_polling()
        session_manager.close()

    async def initialize(self):
        """Inicializa la aplicación (para uso con API)."""
        await self.app.initialize()
        # Initialize plugins asynchronously after app is initialized
        try:
            await self.plugin_manager.initialize(self.app)
        except Exception as e:
            logger.error("Error initializing plugins: %s", e, exc_info=True)

    async def start_async(self):
        """Inicia el bot y el polling de forma asíncrona (para uso con API)."""
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("Bot iniciado en modo asíncrono (API).")

        # Iniciar scheduler de reportes semanales
        try:
            from services.weekly_reports import start_weekly_scheduler

            start_weekly_scheduler(self.app.bot)
            logger.info("Weekly report scheduler iniciado")
        except Exception as e:
            logger.error(f"Error iniciando weekly scheduler: {e}", exc_info=True)

        # Iniciar scheduler de backups diarios
        try:
            from services.backup_scheduler import start_backup_scheduler

            start_backup_scheduler(self.app.bot)
            logger.info("Daily backup scheduler iniciado")
        except Exception as e:
            logger.error(f"Error iniciando daily backup scheduler: {e}", exc_info=True)

        # Iniciar scheduler de reset diario de descargas
        try:
            from services.daily_reset_scheduler import start_daily_reset_scheduler
            from utils.download_limiter import load_downloads

            # Cargar descargas persistidas
            load_downloads()

            # Iniciar scheduler
            start_daily_reset_scheduler(self.app.bot)
            logger.info("Daily reset scheduler iniciado")
        except Exception as e:
            logger.error(f"Error iniciando daily reset scheduler: {e}", exc_info=True)

    async def stop_async(self):
        """Detiene el bot de forma asíncrona."""
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        session_manager.close()
        logger.info("Bot detenido (API).")
