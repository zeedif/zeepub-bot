import logging
import functools
from telegram import Update
from telegram.ext import ContextTypes
from config.config_settings import config

logger = logging.getLogger(__name__)


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_USERS:
            await update.message.reply_text(
                "❌ Este comando es solo para administradores."
            )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


def log_user_action(action_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(
            update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
        ):
            user_id = update.effective_user.id
            username = update.effective_user.username or "unknown"
            logger.info(f"User {user_id} (@{username}) performed action: {action_name}")
            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator


def rate_limit(limit_type: str, max_requests: int = 10, window_seconds: int = 60):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(
            update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
        ):
            # Aquí podrías implementar lógica de rate limiting
            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator
