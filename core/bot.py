import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config.settings import config
from core.state_manager import StateManager
from core.session_manager import SessionManager
from utils.rate_limiter import create_rate_limit_manager_from_config
from utils.rate_limiter import RateLimitType
from handlers.command_handlers import CommandHandlers
from handlers.callback_handlers import CallbackHandlers
from handlers.message_handlers import MessageHandlers
from plugins.plugin_manager import PluginManager


class ZeePubBot:
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.state_manager = StateManager()
        self.session_manager = SessionManager()

        # Usar función helper para crear rate_manager correctamente
        self.rate_manager = create_rate_limit_manager_from_config(config)

        self.plugin_manager = PluginManager()

        self.application = ApplicationBuilder().token(self.token).build()

        # Initialize handler instances
        self.command_handlers = CommandHandlers(self)
        self.callback_handlers = CallbackHandlers(self)
        self.message_handlers = MessageHandlers(self)

    async def start(self):
        # Load plugins
        await self.plugin_manager.initialize(self)

        # Register command handlers
        self.application.add_handler(CommandHandler("start", self.command_handlers.start_command))
        self.application.add_handler(CommandHandler("help", self.command_handlers.help_command))
        self.application.add_handler(CommandHandler("cancel", self.command_handlers.cancel_command))
        self.application.add_handler(CommandHandler("status", self.command_handlers.status_command))
        self.application.add_handler(CommandHandler("plugins", self.command_handlers.plugins_command))

        # Register callback handlers
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.set_destino, pattern="^set_destino"))
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.buscar_epub, pattern="^buscar_epub"))
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.abrir_zeepubs, pattern="^abrir_zeepubs"))
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.button_handler))

        # Register message handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handlers.recibir_texto))

        # Run the bot
        logging.info("Starting the Telegram bot application.")
        await self.application.run_polling()
