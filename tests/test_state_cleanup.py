import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# Prevent circular imports inside the core/handlers modules during test import
sys.modules["core"] = MagicMock()
sys.modules["core.bot"] = MagicMock()
sys.modules["core.state_manager"] = MagicMock()
sys.modules["core.session_manager"] = MagicMock()
# Avoid mocking the callback_handlers module itself; it's the unit under test.
sys.modules["services.opds_service"] = MagicMock()
sys.modules["services.telegram_service"] = MagicMock()
sys.modules["services"] = MagicMock()
sys.modules["utils.http_client"] = MagicMock()
sys.modules["utils.helpers"] = MagicMock()
sys.modules["config.config_settings"] = MagicMock()

import importlib.util
from pathlib import Path

# Load the real callback_handlers module by path to avoid earlier tests stubbing
# `handlers.callback_handlers` in sys.modules. This keeps this unit test isolated.
cb_path = Path(__file__).resolve().parents[1] / "handlers" / "callback_handlers.py"
spec = importlib.util.spec_from_file_location("cb_real_cleanup", str(cb_path))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

import asyncio

@pytest.mark.asyncio
async def test_state_cleanup_on_new_book(monkeypatch):
    uid = 123
    update = MagicMock()
    update.message = MagicMock()
    update.message.edit_message_text = AsyncMock()
    update.message.edit_message_reply_markup = AsyncMock()
    update.message.delete = AsyncMock()
    query = MagicMock()
    query.data = "lib|k1"
    query.message = MagicMock()
    query.message.message_id = 100
    query.message.edit_message_text = AsyncMock()
    query.message.edit_message_reply_markup = AsyncMock()
    query.message.delete = AsyncMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    query.delete = AsyncMock()
    update.callback_query = query
    update.effective_user.id = uid
    update.effective_chat.id = uid
    st = {
        "epub_buffer": b"old",
        "meta_pendiente": {"foo": "bar"},
        "portada_pendiente": "old_url",
        "titulo_pendiente": "old_title",
        "fb_caption": "old_caption",
        "libros": {"k1": {"titulo": "Nuevo", "portada": "url", "descarga": "epub"}},
        "chat_origen": uid,
        "url": "http://example.com/feed",
        "message_thread_id": None
    }
    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)
    monkeypatch.setattr(cb, "config", MagicMock(FACEBOOK_PUBLISHERS={uid}, ADMIN_USERS=set()))
    pub = AsyncMock()
    import sys
    telegram_service_mod = sys.modules.get("services.telegram_service")
    if telegram_service_mod is None:
        from types import ModuleType
        telegram_service_mod = ModuleType("services.telegram_service")
        sys.modules["services.telegram_service"] = telegram_service_mod
    telegram_service_mod.publicar_libro = pub
    monkeypatch.setattr(cb, "publicar_libro", pub)

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_msg = MagicMock()
    send_msg.message_id = 101
    context.bot.send_message = AsyncMock(return_value=send_msg)
    
    # Call handler
    try:
        await cb.button_handler(update, context)
    except Exception as e:
        print(f"Handler raised exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    # All temp keys should be gone
    for k in ("epub_buffer", "meta_pendiente", "portada_pendiente", "titulo_pendiente", "fb_caption"):
        assert k not in st, f"Key '{k}' should have been cleaned up"
