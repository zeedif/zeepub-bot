# handlers/command_handlers.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from core.state_manager import state_manager
from utils.download_limiter import downloads_left, record_download, can_download
from services.opds_service import mostrar_colecciones
from config.config_settings import config
from utils.helpers import get_thread_id, is_command_for_bot, build_search_url
from utils.http_client import parse_feed_from_url

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, app):
        self.app = app
        # Registrar handlers existentes
        app.add_handler(CommandHandler("search", self.search))
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("cancel", self.cancel))
        app.add_handler(CommandHandler("plugins", self.plugins))
        app.add_handler(CommandHandler("evil", self.evil))
        # Registrar /reset
        app.add_handler(CommandHandler("reset", self.reset_command))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start: inicializa estado; admin->evil, otros->normal."""
        
        
        uid = update.effective_user.id
        left = downloads_left(uid)
        text = "👋 ¡Hola! Comencemos.\n\n✅ Tienes descargas ilimitadas." if left == "ilimitadas" else f"👋 ¡Hola! Comencemos.\n\n⚡️ Te quedan {left} descargas hoy."
        
        # Capturar message_thread_id para soporte de topics
        thread_id = get_thread_id(update)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=text,
            message_thread_id=thread_id
        )

        st = state_manager.get_user_state(uid)
        st["destino"] = update.effective_chat.id
        st["chat_origen"] = update.effective_chat.id
        st["message_thread_id"] = thread_id

        # Administradores: mostrar selección de destino Evil directamente
        if uid in config.ADMIN_USERS:
            # Administradores entran directamente en el menú Evil (sin contraseña)
            if uid in config.ADMIN_USERS:
                root = config.OPDS_ROOT_EVIL
                st["opds_root"] = root
                st["opds_root_base"] = root
                st["historial"] = []
                st["ultima_pagina"] = root
#           await context.bot.send_message(
#               chat_id=update.effective_chat.id,
#               text="✅ Elige destino:"
#           )
            # Mostrar opciones de destino
            keyboard = [
                [InlineKeyboardButton("📍 Aquí", callback_data="destino|aqui")],
                [InlineKeyboardButton("📣 BotTest", callback_data="destino|@ZeePubBotTest")],
                [InlineKeyboardButton("📣 ZeePubs", callback_data="destino|@ZeePubs")],
                [InlineKeyboardButton("✏️ Otro", callback_data="destino|otro")]
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔧 Modo Evil: ¿Dónde quieres publicar?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                message_thread_id=thread_id
            )
            return

        # Usuarios normales
        root = config.OPDS_ROOT_START
        st["opds_root"] = root
        st["opds_root_base"] = root
        st["historial"] = []
        st["ultima_pagina"] = root
        await mostrar_colecciones(update, context, root, from_collection=False)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help: muestra ayuda básica."""
        thread_id = get_thread_id(update)
        
        text = (
            "🤖 *Ayuda de ZeePub Bot*\n\n"
            "Aquí tienes lo que puedo hacer por ti:\n\n"
            "/start - 🚀 Comencemos\n"
            "/help - ℹ️ Mostrar esta ayuda\n"
            "/status - 📊 Ver tu estado y descargas\n"
            "/cancel - ❌ Cancelar acción actual\n"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="Markdown",
            message_thread_id=thread_id
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status: informa estado interno, nivel de usuario y descargas restantes."""
        uid = update.effective_user.id
        st = state_manager.get_user_state(uid)
        st = state_manager.get_user_state(uid)

        # Determinar nivel de usuario y máximo de descargas
        if uid in config.PREMIUM_LIST:
            user_level = "Premium"
            max_dl = None  # ilimitadas
        elif uid in config.VIP_LIST:
            user_level = "VIP"
            max_dl = config.VIP_DOWNLOADS_PER_DAY
        elif uid in config.WHITELIST:
            user_level = "Patrocinador"
            max_dl = config.WHITELIST_DOWNLOADS_PER_DAY
        else:
            user_level = "Lector"
            max_dl = config.MAX_DOWNLOADS_PER_DAY

        # Descargas usadas y restantes
        used = st.get("downloads_used", 0)
        if max_dl is None:
            left_text = "✅ Descargas ilimitadas"
        else:
            remaining = max_dl - used
            left_text = f"⚡️ Te quedan {remaining if remaining>0 else 0} descargas por día (de {max_dl})"

        text = (
            "📊 *Tu Estado*\n\n"
            f"👤 *Usuario:* {update.effective_user.first_name}\n"
            f"🆔 *ID:* {uid}\n"
            f"⭐ *Nivel:* {user_level}\n"
            f"📉 *Descargas:* {left_text}\n"
        )

        thread_id = get_thread_id(update)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="Markdown",
            message_thread_id=thread_id
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel: limpia estado, borra menús y confirma cancelación."""
        uid = update.effective_user.id
        st = state_manager.get_user_state(uid)
        
        # Limpiar estado
        st.pop("esperando_busqueda", None)
        st.pop("esperando_destino_manual", None)
        st.pop("series_id", None)
        st.pop("volume_id", None)
        
        chat_id = update.effective_chat.id
        msg_id = update.message.message_id
        
        # Borrar el último mensaje anterior (el menú)
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=msg_id - 1
            )
        except Exception:
            logger.debug("No se pudo borrar mensaje anterior")
        
        # Borrar el mensaje de /cancel
        try:
            await update.message.delete()
        except Exception:
            logger.debug("No se pudo borrar comando /cancel")
        
        thread_id = get_thread_id(update)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ ¡Entendido! Operación cancelada.",
            message_thread_id=thread_id
        )

    async def plugins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /plugins: lista plugins activos."""
        pm = getattr(self.app, "plugin_manager", None)
        if not pm:
            thread_id = get_thread_id(update)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Sistema de plugins no disponible.",
                message_thread_id=thread_id
            )
            return
        plugins = pm.list_plugins()
        if not plugins:
            thread_id = get_thread_id(update)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="📦 No hay plugins activos.",
                message_thread_id=thread_id
            )
            return
        text = "🔌 *Plugins activos:*\n\n"
        for name, info in plugins.items():
            text += f"• *{name}* v{info['version']} — _{info['description']}_\n"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="Markdown"
        )

    async def evil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /evil: inicia modo privado solicitando contraseña."""
        uid = update.effective_user.id
        st = state_manager.get_user_state(uid)
        st["opds_root"] = config.OPDS_ROOT_EVIL
        st["historial"] = []
        st["esperando_password"] = True
        thread_id = get_thread_id(update)
        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔒 Modo Privado. Por favor, ingresa la contraseña:",
            message_thread_id=thread_id
        )
        st["msg_esperando_pwd"] = message.message_id

    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search: busca EPUB con término inline o pide uno."""
        # En grupos con múltiples bots, ignorar si el comando no es para este bot
        bot_username = context.bot.username
        if not is_command_for_bot(update, bot_username):
            return
        
        uid = update.effective_user.id
        st = state_manager.get_user_state(uid)
        thread_id = get_thread_id(update)
        st["message_thread_id"] = thread_id  # Guardar para respuestas
        
        # Verificar si hay término de búsqueda en el comando
        if context.args:
            # Hay término: /search harry potter
            termino = " ".join(context.args).strip()
            logger.debug(f"Usuario {uid} buscando con /search: {termino}")
            
            search_url = build_search_url(termino, uid)
            logger.debug(f"URL de búsqueda: {search_url}")
            feed = await parse_feed_from_url(search_url)
            
            if not feed or not getattr(feed, "entries", []):
                keyboard = [
                    [InlineKeyboardButton("🔄 Volver a buscar", callback_data="buscar")],
                    [InlineKeyboardButton("📚 Ir a colecciones", callback_data="volver_colecciones")],
                ]
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🔍 Mmm, no encontré nada para: {termino}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    message_thread_id=thread_id
                )
            else:
                logger.debug(f"Encontrados {len(feed.entries)} resultados")
                # Asegurar que los resultados aparezcan en el chat actual
                st["destino"] = update.effective_chat.id
                st["chat_origen"] = update.effective_chat.id
                await mostrar_colecciones(update, context, search_url, from_collection=False, new_message=True)
        else:
            # Sin término: pedir uno
            st["esperando_busqueda"] = True
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔍 ¿Qué libro buscas? Escribe el título o autor:",
                message_thread_id=thread_id
            )


    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Resetea el contador de descargas de un usuario (solo admins)."""
        uid = update.effective_user.id

        # Verificar que sea admin
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text("⛔ No tienes permisos para usar este comando.")
            return

        # Verificar argumentos
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "❌ Uso incorrecto.\n"
                "Uso: /reset <user_id>\n"
                "Ejemplo: /reset 123456789"
            )
            return

        try:
            target_uid = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ El ID debe ser un número válido.")
            return

        # Resetear descargas
        user_state = state_manager.get_user_state(target_uid)
        old_count = user_state.get("downloads_used", 0)
        user_state["downloads_used"] = 0

        await update.message.reply_text(
            f"✅ Contador de descargas reseteado para el usuario {target_uid}.\n"
            f"Descargas usadas anteriormente: {old_count}"
        )

        logger.info(f"Admin {uid} reseteó descargas de usuario {target_uid} (antes: {old_count})")
