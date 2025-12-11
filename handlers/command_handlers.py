# handlers/command_handlers.py

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
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
        # Registrar /purge_link (admin only)
        app.add_handler(CommandHandler("purge_link", self.purge_link))
        # Registrar /status_links
        app.add_handler(CommandHandler("status_links", self.status_links))
        # Registrar /link_list
        app.add_handler(CommandHandler("link_list", self.link_list))
        # Debug helper for publishers/admins to inspect their state
        app.add_handler(CommandHandler("debug_state", self.debug_state))
        # Registrar /backup_db y /restore_db (publishers only)
        app.add_handler(CommandHandler("backup_db", self.backup_db))
        app.add_handler(CommandHandler("restore_db", self.restore_db))
        # Registrar /export_db (publishers only)
        app.add_handler(CommandHandler("export_db", self.export_db))
        # Registrar /import_history (admin only)
        app.add_handler(CommandHandler("import_history", self.import_history))
        app.add_handler(CommandHandler("latest_books", self.latest_books))
        app.add_handler(CommandHandler("clear_history", self.clear_history))
        app.add_handler(CommandHandler("export_history", self.export_history))
        # Registrar comandos de donación
        app.add_handler(CommandHandler("donar", self.donate))
        app.add_handler(CommandHandler("donate", self.donate))
        app.add_handler(CommandHandler("niveles", self.niveles))
        app.add_handler(CommandHandler("levels", self.niveles))
        # Registrar /set_price (admin only)
        app.add_handler(CommandHandler("set_price", self.set_price))

        # Registrar comandos de gestión de usuarios (admin)
        app.add_handler(CommandHandler("add_user", self.add_user))
        app.add_handler(CommandHandler("remove_user", self.remove_user))
        app.add_handler(CommandHandler("set_staff_status", self.set_staff_status))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start: inicializa estado; admin->evil, otros->normal."""

        uid = update.effective_user.id
        left = downloads_left(uid)
        text = (
            "👋 ¡Hola! Comencemos.\n\n✅ Tienes descargas ilimitadas."
            if left == "ilimitadas"
            else f"👋 ¡Hola! Comencemos.\n\n⚡️ Te quedan {left} descargas hoy."
        )

        # Capturar message_thread_id para soporte de topics
        thread_id = get_thread_id(update)

        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, message_thread_id=thread_id
        )

        st = state_manager.get_user_state(uid)
        # Limpiar estado temporal de libro anterior al reiniciar
        for k in (
            "epub_buffer",
            "meta_pendiente",
            "portada_pendiente",
            "titulo_pendiente",
            "fb_caption",
        ):
            st.pop(k, None)
        st["destino"] = update.effective_chat.id
        st["chat_origen"] = update.effective_chat.id
        st["message_thread_id"] = thread_id

        # Publishers (ephemeral choice for next book). Admin-only users (not publishers)
        # will be handled separately (go directly to Evil). For users that are both
        # admin+publisher we still show the ephemeral choice here.
        if uid in config.FACEBOOK_PUBLISHERS:
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📨 Publicar en Telegram (próximo libro)",
                        callback_data="set_publish_temp|telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📝 Publicar en Facebook (próximo libro)",
                        callback_data="set_publish_temp|facebook",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⛔ Omitir", callback_data="set_publish_temp|none"
                    )
                ],
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔧 Eres publisher — ¿dónde quieres publicar la próxima vez que selecciones un libro?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                message_thread_id=thread_id,
            )
            # When a publisher sees this choice we must not continue to show
            # the collections menu until they choose where to publish. Defer
            # showing collections until the selection callback runs.
            return

        # Administradores: mostrar selección de destino Evil directamente
        # NOTE: If a user is both admin and publisher we *do not* show the
        # destination menu here. For admin+publisher the ephemeral publish
        # choice shown above will decide whether to show the destination
        # selection (Telegram) or assume "aquí" (Facebook). If the user is an
        # admin but *not* a publisher, we show the Evil menu immediately.
        if uid in config.ADMIN_USERS and uid not in config.FACEBOOK_PUBLISHERS:
            # Administradores entran directamente en el menú Evil (sin contraseña)
            if uid in config.ADMIN_USERS:
                root = config.OPDS_ROOT_EVIL
                st["opds_root"] = root
                st["opds_root_base"] = root
                st["historial"] = []
                st["ultima_pagina"] = root
            # Mostrar opciones de destino
            keyboard = [
                [InlineKeyboardButton("📍 Aquí", callback_data="destino|aqui")],
                [
                    InlineKeyboardButton(
                        "📣 BotTest", callback_data="destino|@ZeePubBotTest"
                    )
                ],
                [InlineKeyboardButton("📣 ZeePubs", callback_data="destino|@ZeePubs")],
                [InlineKeyboardButton("✏️ Otro", callback_data="destino|otro")],
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔧 Modo Evil: ¿Dónde quieres publicar?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                message_thread_id=thread_id,
            )
            return

        # (publisher prompt shown above; continue)

        # Usuarios normales
        root = config.OPDS_ROOT_START
        st["opds_root"] = root
        st["opds_root_base"] = root
        st["historial"] = []
        st["ultima_pagina"] = root
        await mostrar_colecciones(update, context, root, from_collection=False)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help: muestra ayuda dinámica según el rol del usuario."""
        uid = update.effective_user.id
        thread_id = get_thread_id(update)

        # Comandos básicos para todos
        commands = [
            ("🚀 /start", "Iniciar el bot"),
            ("ℹ️ /help", "Mostrar esta ayuda"),
            ("📊 /status", "Ver tu estado y descargas"),
            ("❌ /cancel", "Cancelar acción actual"),
            ("🔍 /search", "Buscar libros"),
            ("☕ /donar", "Link de donación"),
            ("🌟 /niveles", "Info de niveles de usuario"),
        ]

        # Comandos para Publishers (y Admins)
        is_publisher = uid in config.FACEBOOK_PUBLISHERS
        is_admin = uid in config.ADMIN_USERS

        if is_publisher or is_admin:
            commands.extend(
                [
                    ("📤 /export_db", "Exportar mapeo de URLs a CSV"),
                    ("📈 /status_links", "Ver estado de links acortados"),
                    ("📋 /link_list", "Listar links acortados recientes"),
                    (
                        "🗑️ /purge_link",
                        "Eliminar un link acortado (uso: /purge_link <hash>)",
                    ),
                ]
            )

        # Comandos exclusivos de Admin
        if is_admin:
            commands.extend(
                [
                    ("📦 /backup_db", "Generar backup de la base de datos"),
                    ("♻️ /restore_db", "Restaurar base de datos desde archivo"),
                    (
                        "📚 /import_history",
                        "Importar historial desde archivo JSON de Telegram",
                    ),
                    (
                        "🆕 /latest_books",
                        "Ver últimos libros publicados\n"
                        "   • Sin argumentos: todos los libros con su chat_id\n"
                        "   • Con chat_id: solo libros de ese chat\n"
                        "   Ejemplo: /latest_books -1001234567890",
                    ),
                    ("📤 /export_history", "Exportar historial a CSV"),
                    ("🗑️ /clear_history", "Borrar todo el historial (Admin)"),
                    (
                        "➕ /add_user",
                        "Agregar/Editar usuario (Uso: /add_user <id> <rol> [meses])",
                    ),
                    ("➖ /remove_user", "Remover usuario de DB"),
                    (
                        "🏷️ /set_staff_status",
                        "Definir status de Staff (Uso: /set_staff_status <id> <txt>)",
                    ),
                    ("🔄 /reset", "Resetear descargas de usuario (uso: /reset <id>)"),
                    (
                        "💲 /set_price",
                        "Configurar precio de donación (Uso: /set_price <nivel> <monto>)",
                    ),
                    ("🧩 /plugins", "Listar plugins activos"),
                    ("🐞 /debug_state", "Ver estado interno de usuario"),
                ]
            )

        # Construir mensaje
        # Construir mensaje
        text = "🤖 <b>Ayuda de ZeePub Bot</b>\n\nAquí tienes lo que puedo hacer por ti:\n\n"
        for cmd, desc in commands:
            # Escape HTML special chars in description (e.g. <hash>, <id>)
            safe_desc = desc.replace("<", "&lt;").replace(">", "&gt;")
            text += f"<b>{cmd}</b> - {safe_desc}\n"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            message_thread_id=thread_id,
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status: informa estado interno, nivel de usuario y descargas restantes."""
        uid = update.effective_user.id
        st = state_manager.get_user_state(uid)

        # Obtener info extendida
        from services.user_service import get_effective_user

        user_data = get_effective_user(uid)

        roles_display = {
            "admin": "Admin 🛠️",
            "staff": "Staff 🛡️",
            "premium": "Premium ✨",
            "vip": "VIP ⭐️",
            "white": "Patrocinador 🤍",
            "free": "Lector 📚",
        }

        role_key = user_data.get("role", "free")
        status_label = user_data.get("status_label")
        expires_at = user_data.get("expires_at")

        # Override label if custom status exists for staff or just generally
        # The prompt asked for custom status for staff.
        user_level = (
            status_label if status_label else roles_display.get(role_key, "Lector")
        )

        # Max dl logic
        if role_key in ("admin", "staff", "premium"):
            max_dl = None
        elif role_key == "vip":
            max_dl = config.VIP_DOWNLOADS_PER_DAY
        elif role_key == "white":
            max_dl = config.WHITELIST_DOWNLOADS_PER_DAY
        else:
            max_dl = config.MAX_DOWNLOADS_PER_DAY

        # Descargas usadas y restantes
        used = st.get("downloads_used", 0)

        if max_dl is None:
            left_text = "✅ Descargas ilimitadas"
        else:
            remaining = max_dl - used
            left_text = f"⚡️ Te quedan {remaining if remaining>0 else 0} descargas por día (de {max_dl})"
        # Calcular tiempo para próximo reset
        from datetime import datetime, timedelta

        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        time_left = next_midnight - now
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        user_name = update.effective_user.first_name.replace("<", "&lt;").replace(
            ">", "&gt;"
        )

        text = (
            "📊 <b>Tu Estado</b>\n\n"
            f"👤 <b>Usuario:</b> {user_name}\n"
            f"🆔 <b>ID:</b> {uid}\n"
            f"⭐ <b>Nivel:</b> {user_level}\n"
        )

        if expires_at:
            text += f"📅 <b>Vence:</b> {expires_at.strftime('%d/%m/%Y')}\n"

        text += (
            f"📉 <b>Descargas:</b> {left_text}\n"
            f"⏳ <b>Reinicio en:</b> {hours}h {minutes}m\n"
        )

        thread_id = get_thread_id(update)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            message_thread_id=thread_id,
        )

    async def donate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /donar: envía link de donación."""
        thread_id = get_thread_id(update)
        user_name = update.effective_user.first_name
        text = (
            "☕ <b>Apóyanos en Ko-fi</b>\n\n"
            f"Hola {user_name}, gracias por considerar apoyarnos. "
            "Tu ayuda nos permite mantener activo tanto el <b>Bot</b> como el servidor <b>Kavita</b> "
            "y mejorarlos constantemente.\n\n"
            "📝 <b>Instrucciones:</b>\n"
            "1. Haz tu donación en Ko-fi.\n"
            "2. En el mensaje de la donación, puedes incluir un saludo.\n"
            "3. Vuelve aquí y presiona el botón de abajo para avisarnos.\n\n"
            f"👉 <a href='{config.DONATION_URL}'>Haz clic aquí para donar</a>"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Ya realicé la donación", callback_data="notificar_donacion"
                )
            ]
        ]

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            message_thread_id=thread_id,
            disable_web_page_preview=False,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def niveles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /niveles: explica niveles de usuario y beneficios."""
        thread_id = get_thread_id(update)

        from services.settings_service import get_setting

        # Obtener precios dinámicos (con defaults)
        p_white = get_setting("price_whitelist", "5")
        p_vip = get_setting("price_vip", "10")
        p_premium = get_setting("price_premium", "20")
        months = get_setting("benefit_duration_months", "6")

        text = (
            "🌟 <b>Niveles de Usuario y Beneficios</b> 🌟\n\n"
            "Las donaciones nos ayudan a cubrir los costos del servidor. "
            f"Como agradecimiento, otorgamos beneficios por <b>{months} meses</b>.\n\n"
            "🔹 <b>Lector (Gratis)</b>\n"
            f"• {config.MAX_DOWNLOADS_PER_DAY} descargas diarias\n"
            "• Acceso a búsqueda básica\n\n"
            "🔹 <b>Patrocinador</b>\n"
            f"• Donación desde: <b>${p_white} USD</b>\n"
            f"• {config.WHITELIST_DOWNLOADS_PER_DAY} descargas diarias\n"
            "• Acceso prioritario\n\n"
            "🔹 <b>VIP</b>\n"
            f"• Donación desde: <b>${p_vip} USD</b>\n"
            f"• {config.VIP_DOWNLOADS_PER_DAY} descargas diarias\n"
            "• Soporte directo\n"
            "• 📱 Acceso a Mini App\n\n"
            "🔹 <b>Premium</b>\n"
            f"• Donación desde: <b>${p_premium} USD</b>\n"
            "• ♾️ <b>Descargas Ilimitadas</b>\n"
            "• 📱 Acceso a Mini App\n"
            "• Acceso a funciones exclusivas futuras\n\n"
            "💳 Usa /donar para obtener el link de Ko-fi.\n"
            "<i>(Los montos ayudan a mantener el proyecto vivo ❤️)</i>"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            message_thread_id=thread_id,
        )

    async def set_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configura el precio de donación para un nivel (solo admins)."""
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text("⛔ No tienes permisos.")
            return

        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                "❌ Uso: /set_price <nivel> <monto>\n"
                "Niveles: white, vip, premium, meses\n"
                "Ejemplo: /set_price vip 15"
            )
            return

        level = context.args[0].lower()
        amount = context.args[1]

        # Validar que amount sea número (o al menos string razonable)
        if not amount.isdigit() and not amount.replace(".", "", 1).isdigit():
            await update.message.reply_text("❌ El monto debe ser un número.")
            return

        key_map = {
            "white": "price_whitelist",
            "patrocinador": "price_whitelist",
            "vip": "price_vip",
            "premium": "price_premium",
            "meses": "benefit_duration_months",
            "duration": "benefit_duration_months",
        }

        if level not in key_map:
            await update.message.reply_text(
                "❌ Nivel inválido. Usa: white, vip, premium, meses"
            )
            return

        from services.settings_service import set_setting

        set_setting(key_map[level], amount)

        if level in ("meses", "duration"):
            msg_text = f"✅ Duración de beneficios actualizada a: <b>{amount} meses</b>"
        else:
            msg_text = (
                f"✅ Precio para <b>{level}</b> actualizado a: <b>${amount} USD</b>"
            )

        await update.message.reply_text(msg_text, parse_mode="HTML")

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
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id - 1)
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
            message_thread_id=thread_id,
        )

    async def plugins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /plugins: lista plugins activos."""
        pm = getattr(self.app, "plugin_manager", None)
        if not pm:
            thread_id = get_thread_id(update)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Sistema de plugins no disponible.",
                message_thread_id=thread_id,
            )
            return
        plugins = pm.list_plugins()
        if not plugins:
            thread_id = get_thread_id(update)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="📦 No hay plugins activos.",
                message_thread_id=thread_id,
            )
            return
        text = "🔌 <b>Plugins activos:</b>\n\n"
        for name, info in plugins.items():
            safe_name = name.replace("<", "&lt;").replace(">", "&gt;")
            safe_desc = info["description"].replace("<", "&lt;").replace(">", "&gt;")
            text += f"• <b>{safe_name}</b> v{info['version']} — <i>{safe_desc}</i>\n"
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, parse_mode="HTML"
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
            message_thread_id=thread_id,
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
                    [
                        InlineKeyboardButton(
                            "🔄 Volver a buscar", callback_data="buscar"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📚 Ir a colecciones", callback_data="volver_colecciones"
                        )
                    ],
                ]
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🔍 Mmm, no encontré nada para: {termino}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    message_thread_id=thread_id,
                )
            else:
                logger.debug(f"Encontrados {len(feed.entries)} resultados")
                # Asegurar que los resultados aparezcan en el chat actual
                st["destino"] = update.effective_chat.id
                st["chat_origen"] = update.effective_chat.id
                await mostrar_colecciones(
                    update, context, search_url, from_collection=False, new_message=True
                )
        else:
            # Sin término: pedir uno
            st["esperando_busqueda"] = True
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔍 ¿Qué libro buscas? Escribe el título o autor:",
                message_thread_id=thread_id,
            )

    async def purge_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Elimina un link acortado de la caché (solo publishers)."""
        uid = update.effective_user.id

        # Verificar que sea publisher
        if uid not in config.FACEBOOK_PUBLISHERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        # Verificar argumentos
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "❌ Uso incorrecto.\n"
                "Uso: /purge_link <hash>\n"
                "Ejemplo: /purge_link abcdefg"
            )
            return

        hash_to_purge = context.args[0]

        try:
            # Use the same database-agnostic approach as other url_cache functions
            if config.DATABASE_URL:
                # PostgreSQL backend
                try:
                    import sqlalchemy as sa
                    from sqlalchemy import Table, MetaData

                    engine = sa.create_engine(
                        config.DATABASE_URL, future=True, pool_pre_ping=True
                    )
                    metadata = MetaData()
                    url_mappings = Table("url_mappings", metadata, autoload_with=engine)

                    with engine.begin() as conn:
                        # Check if exists
                        sel = sa.select(url_mappings.c.hash).where(
                            url_mappings.c.hash == hash_to_purge
                        )
                        result = conn.execute(sel).first()

                        if result:
                            # Delete it
                            delete_stmt = url_mappings.delete().where(
                                url_mappings.c.hash == hash_to_purge
                            )
                            conn.execute(delete_stmt)

                            await update.message.reply_text(
                                f"✅ Link con hash <code>{hash_to_purge}</code> eliminado de la caché.",
                                parse_mode="HTML",
                            )
                            logger.info(
                                f"Admin {uid} eliminó link {hash_to_purge} de la caché (PostgreSQL)."
                            )
                        else:
                            await update.message.reply_text(
                                f"ℹ️ No se encontró ningún link con hash <code>{hash_to_purge}</code> en la caché.",
                                parse_mode="HTML",
                            )
                except Exception as e:
                    logger.error(
                        f"PostgreSQL error in purge_link, falling back to SQLite: {e}"
                    )
                    raise  # Re-raise to trigger the SQLite fallback below
            else:
                # SQLite backend
                from utils.url_cache import DB_PATH
                import sqlite3

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM url_mappings WHERE hash = ?", (hash_to_purge,)
                )
                rows_deleted = cursor.rowcount
                conn.commit()
                conn.close()

                if rows_deleted > 0:
                    await update.message.reply_text(
                        f"✅ Link con hash <code>{hash_to_purge}</code> eliminado de la caché.",
                        parse_mode="HTML",
                    )
                    logger.info(
                        f"Admin {uid} eliminó link {hash_to_purge} de la caché (SQLite)."
                    )
                else:
                    await update.message.reply_text(
                        f"ℹ️ No se encontró ningún link con hash <code>{hash_to_purge}</code> en la caché.",
                        parse_mode="HTML",
                    )

        except Exception as e:
            logger.error(
                f"Error en purge_link para hash {hash_to_purge}: {e}", exc_info=True
            )
            await update.message.reply_text(
                f"❌ Error al intentar eliminar el link: {str(e)}"
            )

    async def add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /add_user <id> <rol> [meses]
        Agrega un usuario con un rol específico y duración opcional.
        """
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Uso: /add_user <id> <rol> [meses]\n"
                "Roles: white, vip, premium, staff\n"
                "Ejemplo: /add_user 123456789 vip 6"
            )
            return

        target_id_str = context.args[0]
        role = context.args[1].lower()

        if not target_id_str.isdigit():
            await update.message.reply_text("❌ ID inválido.")
            return
        target_id = int(target_id_str)

        valid_roles = ["white", "vip", "premium", "staff"]
        if role not in valid_roles:
            await update.message.reply_text(
                f"❌ Rol inválido. Use: {', '.join(valid_roles)}"
            )
            return

        # Determine duration
        duration = None
        if len(context.args) >= 3:
            if context.args[2].isdigit():
                duration = int(context.args[2])
        else:
            # Use default from settings if not provided
            # Only for non-staff roles usually, but consistent behavior is better
            if role != "staff":
                from services.settings_service import get_setting

                duration = int(get_setting("benefit_duration_months", "6"))

        from services.user_service import upsert_user

        upsert_user(target_id, role, duration_months=duration, created_by=uid)

        msg = f"✅ Usuario <code>{target_id}</code> agregado como <b>{role.capitalize()}</b>"
        if duration:
            msg += f" por <b>{duration} meses</b>."
        else:
            msg += " (Permanente/Hasta cancelación)."

        await update.message.reply_text(msg, parse_mode="HTML")

    async def remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /remove_user <id>
        Elimina un usuario de la base de datos (revoca rol dinámico).
        """
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("❌ Uso: /remove_user <id>")
            return

        target_id_str = context.args[0]
        if not target_id_str.isdigit():
            await update.message.reply_text("❌ ID inválido.")
            return
        target_id = int(target_id_str)

        from services.user_service import remove_user

        remove_user(target_id)

        await update.message.reply_text(
            f"✅ Usuario <code>{target_id}</code> removido de la DB.", parse_mode="HTML"
        )

    async def set_staff_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        /set_staff_status <id> <texto>
        Establece un status personalizado para un usuario Staff.
        """
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Uso: /set_staff_status <id> <texto status>"
            )
            return

        target_id_str = context.args[0]
        if not target_id_str.isdigit():
            await update.message.reply_text("❌ ID inválido.")
            return
        target_id = int(target_id_str)

        status_text = " ".join(context.args[1:])

        from services.user_service import get_user_info, upsert_user

        info = get_user_info(target_id)
        if not info:
            await update.message.reply_text(
                "❌ El usuario no existe en la DB. Úsalo primero con /add_user."
            )
            return

        current_role = info.get("role")
        upsert_user(target_id, current_role, custom_status=status_text, created_by=uid)

        await update.message.reply_text(
            f"✅ Status de <code>{target_id}</code> actualizado a: <b>{status_text}</b>",
            parse_mode="HTML",
        )

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Existing reset command implementation
        """Resetea el contador de descargas de un usuario (solo admins)."""
        uid = update.effective_user.id

        # Verificar que sea admin
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
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
        from utils.download_limiter import save_download

        user_state = state_manager.get_user_state(target_uid)
        old_count = user_state.get("downloads_used", 0)
        user_state["downloads_used"] = 0

        # Actualizar persistencia
        save_download(target_uid, 0)

        await update.message.reply_text(
            f"✅ Contador de descargas reseteado para el usuario {target_uid}.\n"
            f"Descargas usadas anteriormente: {old_count}"
        )

        logger.info(
            f"Admin {uid} reseteó descargas de usuario {target_uid} (antes: {old_count})"
        )

    async def status_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra estado de los links acortados (solo publishers)."""
        uid = update.effective_user.id

        # Verificar permisos (solo publishers)
        if uid not in config.FACEBOOK_PUBLISHERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        thread_id = get_thread_id(update)

        # Enviar mensaje de "procesando"
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔄 Obteniendo estadísticas...",
            message_thread_id=thread_id,
        )

        try:
            from utils.url_cache import (
                get_stats,
                get_broken_links,
                validate_and_update_url,
                get_url_from_hash,
                get_recent_links,
                DB_PATH,
            )
            import asyncio
            import sqlite3

            # Validar solo 5 links recientes (reducido de 20 para evitar timeouts)
            recent_links = get_recent_links(limit=5)

            # Validar con timeout de 10 segundos total para evitar bloquear el bot
            if recent_links:
                try:
                    tasks = [
                        validate_and_update_url(item[0], item[1])
                        for item in recent_links
                    ]
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout validating links in status_links")

            # Actualizar estadísticas después de la validación
            stats = get_stats()
            broken = get_broken_links(limit=5)

            # Construir reporte
            success_rate = (
                (stats["valid"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )

            report = "🔍 <b>Estado de Links Acortados</b>\n\n"
            report += "📊 <b>Estadísticas:</b>\n"
            report += f"  • Total: {stats['total']} links\n"
            report += f"  ✅ Válidos: {stats['valid']}\n"
            report += f"  ❌ Rotos: {stats['broken']}\n"
            report += f"  ⚠️ En riesgo: {stats['at_risk']} (2 fallos)\n"
            report += f"  📈 Tasa de éxito: {success_rate:.1f}%\n"

            if broken:
                report += "\n⚠️ <b>Links Rotos (máximo 5):</b>\n"
                for hash_val, title, failed, last_checked in broken:
                    title_short = (
                        (title[:40] + "...")
                        if title and len(title) > 40
                        else (title or "Sin título")
                    )

                    # Obtener fecha de creación
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT created_at FROM url_mappings WHERE hash = ?",
                        (hash_val,),
                    )
                    created_row = cursor.fetchone()
                    conn.close()
                    created_date = created_row[0] if created_row else "Desconocida"

                    report += f"  • {title_short}\n"
                    report += f"    Hash: <code>{hash_val}</code>\n"
                    report += f"    Creado: {created_date}\n"
                    report += f"    Fallos: {failed}/3\n"

            report += "\n📄 <i>Nota: Se validaron los últimos 5 links. Para revisar todos usa el validador automático.</i>"

            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text=report,
                parse_mode="HTML",
            )

        except Exception as e:
            logger.error(f"Error en status_links: {e}", exc_info=True)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text=f"❌ Error al obtener estado de links: {str(e)}",
            )

    async def link_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra listado de links acortados recientes (solo publishers)."""
        uid = update.effective_user.id

        # Verificar permisos (solo publishers)
        if uid not in config.FACEBOOK_PUBLISHERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        thread_id = get_thread_id(update)

        # Determinar límite (argumento opcional)
        limit = 10  # default
        if context.args:
            try:
                limit = int(context.args[0])
                limit = min(max(limit, 1), 50)  # Entre 1 y 50
            except ValueError:
                await update.message.reply_text(
                    "❌ El límite debe ser un número. Uso: /link_list [número]"
                )
                return

        try:
            from utils.url_cache import get_recent_links

            recent_links = get_recent_links(limit=limit)

            if not recent_links:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="ℹ️ No hay links en la caché.",
                    message_thread_id=thread_id,
                )
                return

            # Construir mensaje
            report = (
                f"📋 <b>Links Acortados Recientes</b> (últimos {len(recent_links)})\n\n"
            )

            for i, (hash_val, url, book_title, created_at) in enumerate(
                recent_links, 1
            ):
                title_display = (
                    (book_title[:45] + "...")
                    if book_title and len(book_title) > 45
                    else (book_title or "Sin título")
                )

                # Construir link acortado
                dl_domain = config.DL_DOMAIN.rstrip("/")
                if not dl_domain.startswith("http"):
                    dl_domain = f"https://{dl_domain}"
                short_link = f"{dl_domain}/api/dl/{hash_val}"

                report += f"{i}. <b>{title_display}</b>\n"
                report += f"   Hash: <code>{hash_val}</code>\n"
                report += f"   Link: {short_link}\n"
                report += f"   Creado: {created_at or 'Desconocido'}\n\n"

            report += "<i>💡 Usa /purge_link &lt;hash&gt; para eliminar un link específico.</i>"

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=report,
                parse_mode="HTML",
                message_thread_id=thread_id,
            )

        except Exception as e:
            logger.error(f"Error en link_list: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Error al obtener listado de links: {str(e)}",
                message_thread_id=thread_id,
            )

    async def debug_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Debug command to show a snapshot of the user's state (admins only)."""
        uid = update.effective_user.id

        # Only allow admins
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ Solo administradores pueden usar /debug_state."
            )
            return

        st = state_manager.get_user_state(uid)
        # Build a compact, safe state summary
        keys = [
            "destino",
            "chat_origen",
            "message_thread_id",
            "titulo_pendiente",
            "portada_pendiente",
            "pending_pub_book",
            "pending_pub_menu_prep",
            "awaiting_publish_target",
            "publish_command_origin",
            "publish_command_thread_id",
            "msg_botones_id",
            "msg_info_id",
            "epub_url",
        ]
        parts = [
            f"👤 ID: {uid}",
            f"⭐ is_admin: {uid in config.ADMIN_USERS}",
            f"📝 is_publisher: {uid in config.FACEBOOK_PUBLISHERS}",
        ]
        for k in keys:
            v = st.get(k)
            # Make values short for readability
            if isinstance(v, (str, int)) or v is None:
                parts.append(f"{k}: {v}")
            else:
                try:
                    # For dicts/lists show length or keys
                    if isinstance(v, dict):
                        parts.append(f"{k}: dict(keys={list(v.keys())})")
                    elif isinstance(v, list):
                        parts.append(f"{k}: list(len={len(v)})")
                    else:
                        parts.append(f"{k}: {repr(v)[:80]}")
                except Exception:
                    parts.append(f"{k}: <unprintable>")

        text = "\n".join(parts)
        thread_id = get_thread_id(update)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🧭 Estado (parcial):\n\n{text}",
            message_thread_id=thread_id,
        )

    async def backup_db(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Realiza un backup de la base de datos (solo admins)."""
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        thread_id = get_thread_id(update)
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏳ Generando backup...",
            message_thread_id=thread_id,
        )

        try:
            from services.backup_service import generate_backup_file

            filename = await generate_backup_file()

            # Enviar archivo
            with open(filename, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=filename,
                    caption=f"📦 Backup de base de datos\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    message_thread_id=thread_id,
                )

            # Limpiar
            try:
                os.remove(filename)
            except Exception:
                logger.debug("No se pudo eliminar backup temporal: %s", filename)

            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=msg.message_id
            )

        except Exception as e:
            logger.error(f"Error en backup_db: {e}", exc_info=True)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text=f"❌ Error al generar backup: {str(e)}",
            )

    async def restore_db(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restaura la base de datos desde un archivo (solo admins)."""
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        if (
            not update.message.reply_to_message
            or not update.message.reply_to_message.document
        ):
            await update.message.reply_text(
                "⚠️ Debes responder a un mensaje con el archivo .sql de backup para restaurarlo."
            )
            return

        doc = update.message.reply_to_message.document
        # Validación de extensión movida dentro de la lógica específica de DB
        # if not doc.file_name.endswith(".sql"):
        #     await update.message.reply_text("⚠️ El archivo debe tener extensión .sql")
        #     return

        thread_id = get_thread_id(update)
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏳ Descargando y restaurando backup... (Esto borrará los datos actuales)",
            message_thread_id=thread_id,
        )

        try:

            # Descargar archivo
            file = await doc.get_file()

            if config.DATABASE_URL:
                # --- Lógica PostgreSQL ---
                if not doc.file_name.endswith(".sql"):
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=msg.message_id,
                        text="⚠️ Para PostgreSQL, el archivo debe ser un .sql",
                    )
                    return

                filename = f"restore_{doc.file_name}"
                await file.download_to_drive(filename)

                # Obtener credenciales (igual que backup)
                pg_user = os.getenv("POSTGRES_USER")
                pg_password = os.getenv("POSTGRES_PASSWORD")
                pg_db = os.getenv("POSTGRES_DB")
                pg_host = "db"

                if not pg_user:
                    try:
                        from sqlalchemy.engine import make_url

                        url = make_url(config.DATABASE_URL)
                        pg_user = url.username
                        pg_password = url.password
                        if url.host:
                            pg_host = url.host
                        pg_db = url.database
                    except Exception:
                        pass

                if not pg_user or not pg_password:
                    raise Exception("No se encontraron credenciales de base de datos.")

                # Configurar entorno
                env = os.environ.copy()
                env["PGPASSWORD"] = pg_password

                # Comando psql para restaurar
                cmd = [
                    "psql",
                    "-h",
                    pg_host,
                    "-U",
                    pg_user,
                    "-d",
                    pg_db,
                    "-f",
                    filename,
                ]

                # Use asyncio subprocess
                import asyncio as _asyncio

                proc = await _asyncio.create_subprocess_exec(
                    *cmd,
                    env=env,
                    stdout=_asyncio.subprocess.PIPE,
                    stderr=_asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await _asyncio.wait_for(
                        proc.communicate(), timeout=180
                    )
                except _asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise Exception("psql restore timed out")
                if proc.returncode != 0:
                    raise Exception(f"Restore failed: {stderr.decode(errors='ignore')}")

                try:
                    os.remove(filename)
                except Exception:
                    logger.debug(
                        "No se pudo eliminar archivo temporal de restore: %s", filename
                    )

            else:
                # --- Lógica SQLite ---
                # Validar extensión (opcional, pero recomendable)
                if not (
                    doc.file_name.endswith(".db") or doc.file_name.endswith(".sqlite")
                ):
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=msg.message_id,
                        text="⚠️ Para SQLite, el archivo debe ser .db o .sqlite",
                    )
                    return

                # Sobrescribir el archivo de base de datos
                db_path = config.URL_CACHE_DB_PATH

                # Backup de seguridad antes de sobrescribir
                if os.path.exists(db_path):
                    backup_path = f"{db_path}.bak"
                    import shutil

                    shutil.copy2(db_path, backup_path)

                await file.download_to_drive(db_path)

            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text="✅ Base de datos restaurada exitosamente.",
            )
            logger.info(
                f"Publisher {uid} restauró la base de datos desde {doc.file_name}"
            )

        except Exception as e:
            logger.error(f"Error en restore_db: {e}", exc_info=True)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text=f"❌ Error al restaurar backup: {str(e)}",
            )

    async def export_db(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exporta la base de datos a CSV (solo publishers)."""
        uid = update.effective_user.id
        if uid not in config.FACEBOOK_PUBLISHERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        thread_id = get_thread_id(update)
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏳ Generando CSV de la base de datos...",
            message_thread_id=thread_id,
        )

        try:
            import csv

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"export_db_{timestamp}.csv"

            # Determinar si usar PostgreSQL o SQLite
            if config.DATABASE_URL:
                # PostgreSQL usando SQLAlchemy
                from sqlalchemy import create_engine, text

                engine = create_engine(config.DATABASE_URL)

                with engine.connect() as conn:
                    result = conn.execute(
                        text("SELECT * FROM url_mappings ORDER BY created_at DESC")
                    )
                    rows = result.fetchall()
                    columns = result.keys()

                # Escribir CSV en thread pool para no bloquear el loop
                import asyncio as _asyncio

                def _write_csv(path, columns, rows):
                    with open(path, "w", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(columns)
                        writer.writerows(rows)

                await _asyncio.to_thread(_write_csv, filename, columns, rows)

            else:
                # SQLite
                import sqlite3
                from utils.url_cache import DB_PATH

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM url_mappings ORDER BY created_at DESC")
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                conn.close()

                # Escribir CSV en thread pool para no bloquear el loop
                import asyncio as _asyncio

                def _write_csv(path, columns, rows):
                    with open(path, "w", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(columns)
                        writer.writerows(rows)

                await _asyncio.to_thread(_write_csv, filename, columns, rows)

            # Enviar archivo cerrando descriptor cuando termine
            with open(filename, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=filename,
                    caption=f"📊 Exportación de base de datos\n📅 {timestamp}\n📦 {len(rows)} registros",
                    message_thread_id=thread_id,
                )

            try:
                os.remove(filename)
            except Exception:
                logger.debug("No se pudo eliminar CSV temporal: %s", filename)
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=msg.message_id
            )

        except Exception as e:
            logger.error(f"Error en export_db: {e}", exc_info=True)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                text=f"❌ Error al generar CSV: {str(e)}",
            )

    async def import_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activa el modo de importación de historial (solo admins)."""
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        st = state_manager.get_user_state(uid)
        st["waiting_for_history_json"] = True

        await update.message.reply_text(
            "📂 <b>Modo de Importación Activado</b>\n\n"
            "Por favor, envía ahora el archivo <code>result.json</code> exportado de Telegram Desktop.\n"
            "El bot procesará el archivo y guardará el historial de libros publicados.\n\n"
            "<i>Este modo se desactivará automáticamente después de recibir el archivo.</i>",
            parse_mode="HTML",
        )

    async def latest_books(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra los últimos 10 libros importados/publicados (solo admins).

        Uso:
            /latest_books              -> Muestra todos los últimos 10 libros
            /latest_books <chat_id>    -> Filtra por chat_id específico
        """
        uid = update.effective_user.id

        # Restricción: solo admins
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        try:
            from services.history_service import get_latest_books

            # Parse argumentos: chat_id opcional
            channel_filter = None
            if context.args and len(context.args) > 0:
                try:
                    channel_filter = int(context.args[0])
                except ValueError:
                    await update.message.reply_text(
                        "❌ Chat ID inválido. Uso: /latest_books [chat_id]\n"
                        "Ejemplo: /latest_books -1001234567890"
                    )
                    return

            # Obtener libros con o sin filtro
            books = get_latest_books(limit=10, channel_id=channel_filter)

            if not books:
                if channel_filter:
                    await update.message.reply_text(
                        f"📚 No hay libros registrados en el chat {channel_filter}."
                    )
                else:
                    await update.message.reply_text(
                        "📚 No hay libros registrados en el historial."
                    )
                return

            # Título del mensaje según modo
            if channel_filter:
                text = f"📚 <b>Últimos 10 Libros en Chat {channel_filter}</b>\n\n"
            else:
                text = "📚 <b>Últimos 10 Libros Publicados</b>\n\n"

            for b in books:
                # b is a Row object (title, author, series, slug, date, ..., channel_id)
                title = b.title or "Sin título"
                author = b.author or "Desconocido"
                series = f" ({b.series})" if b.series else ""
                date_str = (
                    b.date_published.strftime("%Y-%m-%d %H:%M")
                    if b.date_published
                    else "?"
                )

                text += f"🔹 <b>{title}</b>{series}\n"
                text += f"   ✍️ {author}\n"
                text += f"   📅 {date_str} | #️⃣ {b.slug}\n"

                # Mostrar chat_id si NO estamos filtrando (modo sin argumentos)
                if not channel_filter and hasattr(b, "channel_id") and b.channel_id:
                    text += f"   📍 Chat: {b.channel_id}\n"

                text += "\n"

            await update.message.reply_text(text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Error in latest_books: {e}")
            await update.message.reply_text("❌ Error al obtener el historial.")

    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Borra todo el historial de libros publicados (solo admin)."""
        uid = update.effective_user.id
        if uid not in config.ADMIN_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        # Confirmación simple (podría ser mejor con botones, pero por ahora texto)
        if not context.args or context.args[0] != "confirm":
            await update.message.reply_text(
                "⚠️ <b>¡ATENCIÓN!</b> Esto borrará TODO el historial de libros publicados.\n"
                "Para confirmar, usa: <code>/clear_history confirm</code>",
                parse_mode="HTML",
            )
            return

        try:
            from services.history_service import clear_history

            if clear_history():
                await update.message.reply_text("✅ Historial borrado exitosamente.")
            else:
                await update.message.reply_text("❌ Error al borrar el historial.")
        except Exception as e:
            logger.error(f"Error in clear_history: {e}")
            await update.message.reply_text(
                "❌ Error inesperado al borrar el historial."
            )

    async def export_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exporta el historial de libros publicados a CSV."""
        uid = update.effective_user.id
        # Allow publishers and admins
        if uid not in config.ADMIN_USERS and uid not in config.PUBLISHER_USERS:
            await update.message.reply_text(
                "⛔ No tienes permisos para usar este comando."
            )
            return

        try:
            from services.history_service import get_latest_books

            # Get all books (set a high limit)
            books = get_latest_books(limit=10000)

            if not books:
                await update.message.reply_text(
                    "📚 No hay libros registrados en el historial."
                )
                return

            # Create CSV
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow(
                [
                    "Título",
                    "Maquetado por",
                    "Demografía",
                    "Géneros",
                    "Autor",
                    "Serie",
                    "Slug",
                    "Ilustrador",
                    "Traducción",
                    "Fecha Publicación",
                    "Tamaño",
                ]
            )

            # Data
            for b in books:
                # Format file size if available
                file_size_str = ""
                if hasattr(b, "file_size") and b.file_size:
                    # Convert bytes to MB
                    file_size_mb = b.file_size / (1024 * 1024)
                    file_size_str = f"{file_size_mb:.2f} MB"

                writer.writerow(
                    [
                        b.title or "Unknown",
                        b.maquetado_por or "" if hasattr(b, "maquetado_por") else "",
                        b.demografia or "" if hasattr(b, "demografia") else "",
                        b.generos or "" if hasattr(b, "generos") else "",
                        b.author or "Desconocido",
                        b.series or "",
                        b.slug or "",
                        b.ilustrador or "" if hasattr(b, "ilustrador") else "",
                        b.traduccion or "" if hasattr(b, "traduccion") else "",
                        (
                            b.date_published.strftime("%Y-%m-%d %H:%M")
                            if b.date_published
                            else ""
                        ),
                        file_size_str,
                    ]
                )

            # Send as file
            csv_bytes = output.getvalue().encode("utf-8")
            await update.message.reply_document(
                document=csv_bytes,
                filename="historial_libros.csv",
                caption=f"📊 Historial de {len(books)} libros publicados",
            )

        except Exception as e:
            logger.error(f"Error in export_history: {e}")
            await update.message.reply_text("❌ Error al exportar el historial.")
