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
spec = importlib.util.spec_from_file_location("cb_real", str(cb_path))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


@pytest.mark.asyncio
async def test_set_publish_temp_stores_one_time_choice(monkeypatch):
    uid = 111

    # prepare a mutable state dict
    st = {}
    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)

    # prepare update/context mocks
    update = MagicMock()
    query = MagicMock()
    query.data = "set_publish_temp|telegram"
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()
    update.callback_query = query
    update.effective_user.id = uid

    # ensure mostrar_colecciones is a coroutine so await works
    monkeypatch.setattr(cb, "mostrar_colecciones", AsyncMock())
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    await cb.button_handler(update, context)

    assert st.get("publish_target_temp") == "telegram"


@pytest.mark.asyncio
async def test_publish_temp_consumed_on_lib_selection_calls_telegram(monkeypatch):
    uid = 222
    libro_key = "k1"
    update = MagicMock()
    update.message = MagicMock()
    update.message.edit_message_text = AsyncMock()
    update.message.edit_message_reply_markup = AsyncMock()
    update.message.delete = AsyncMock()
    query = MagicMock()
    query.data = f"lib|{libro_key}"
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
    libro = {"titulo": "Mi Libro", "portada": "http://x/cover.jpg", "descarga": "http://x/book.epub"}
    st = {
        "libros": {libro_key: libro},
        "publish_target_temp": "telegram",
        "chat_origen": uid,
        "url": "http://example.com/feed",
        "message_thread_id": None
    }

    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)
    monkeypatch.setattr(cb, "config", MagicMock(FACEBOOK_PUBLISHERS={uid}, ADMIN_USERS=set()))

    # Patch publicar_libro in the actual import path used by the handler
    import sys
    telegram_service_mod = sys.modules.get("services.telegram_service")
    if telegram_service_mod is None:
        from types import ModuleType
        telegram_service_mod = ModuleType("services.telegram_service")
        sys.modules["services.telegram_service"] = telegram_service_mod
    pub = AsyncMock()
    telegram_service_mod.publicar_libro = pub
    monkeypatch.setattr(cb, "publicar_libro", pub)

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_msg = MagicMock()
    send_msg.message_id = 101
    context.bot.send_message = AsyncMock(return_value=send_msg)

    await cb.button_handler(update, context)

    assert pub.called
    assert "publish_target_temp" not in st


@pytest.mark.asyncio
async def test_admin_publisher_set_publish_temp_fb_enters_evil(monkeypatch):
    uid = 444

    st = {}
    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)

    # user is admin and publisher
    monkeypatch.setattr(cb, "config", MagicMock(FACEBOOK_PUBLISHERS={uid}, ADMIN_USERS={uid}, OPDS_ROOT_EVIL="/opds-evil"))

    # intercept mostrar_colecciones
    mc = AsyncMock()
    monkeypatch.setattr(cb, "mostrar_colecciones", mc)

    update = MagicMock()
    query = MagicMock()
    query.data = "set_publish_temp|facebook"
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()
    update.callback_query = query
    update.effective_user.id = uid
    update.effective_chat.id = uid

    context = MagicMock()

    await cb.button_handler(update, context)

    # OPDS root should be switched to evil and mostrar_colecciones called
    assert st.get("opds_root") == "/opds-evil"
    assert st.get("destino") == uid
    assert mc.called


@pytest.mark.asyncio
async def test_start_publisher_does_not_show_collections_immediately(monkeypatch):
    uid = 666

    # Prepare /start handler test: ensure publishers only see the ephemeral
    # publish-choice and do NOT have mostrar_colecciones called immediately.
    import importlib, inspect
    ch_path = Path(__file__).resolve().parents[1] / "handlers" / "command_handlers.py"
    spec = importlib.util.spec_from_file_location("ch_mod", str(ch_path))
    ch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ch)

    # Patch state_manager, downloads_left and mostrar_colecciones
    st = {}
    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(ch, "state_manager", mock_state)
    # avoid downloads_left using core.state_manager/config inside ch
    monkeypatch.setattr(ch, "downloads_left", lambda uid: "ilimitadas")
    mc = AsyncMock()
    monkeypatch.setattr(ch, "mostrar_colecciones", mc)

    # config: user is publisher
    monkeypatch.setattr(ch, "config", MagicMock(FACEBOOK_PUBLISHERS={uid}, ADMIN_USERS=set(), OPDS_ROOT_START="/opds-start"))

    # update/context
    update = MagicMock()
    update.effective_user.id = uid
    update.effective_chat.id = uid
    update.effective_chat.type = 'private'
    context = MagicMock()
    # Provide an async send_message for the fake bot used in the handler
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    dummy_app = MagicMock()
    await ch.CommandHandlers(dummy_app).start(update, context)

    # mostrar_colecciones should NOT have been called (we deferred showing)
    assert not mc.called


@pytest.mark.asyncio
async def test_publish_temp_consumed_on_lib_selection_calls_facebook(monkeypatch):
    uid = 333
    libro_key = "k2"
    update = MagicMock()
    update.message = MagicMock()
    update.message.edit_message_text = AsyncMock()
    update.message.edit_message_reply_markup = AsyncMock()
    update.message.delete = AsyncMock()
    query = MagicMock()
    query.data = f"lib|{libro_key}"
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
    libro = {"titulo": "Libro 2", "portada": "http://x/cover2.jpg", "descarga": "http://x/book2.epub"}
    st = {
        "libros": {libro_key: libro},
        "publish_target_temp": "facebook",
        "chat_origen": uid,
        "url": "http://example.com/feed",
        "message_thread_id": None
    }

    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)
    monkeypatch.setattr(cb, "config", MagicMock(FACEBOOK_PUBLISHERS={uid}, ADMIN_USERS=set()))

    # Patch _publish_choice_facebook in the actual import path used by the handler
    import sys
    telegram_service_mod = sys.modules.get("services.telegram_service")
    if telegram_service_mod is None:
        from types import ModuleType
        telegram_service_mod = ModuleType("services.telegram_service")
        sys.modules["services.telegram_service"] = telegram_service_mod
    facebook = AsyncMock()
    telegram_service_mod._publish_choice_facebook = facebook

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_msg = MagicMock()
    send_msg.message_id = 101
    context.bot.send_message = AsyncMock(return_value=send_msg)

    await cb.button_handler(update, context)

    assert facebook.called
    assert "publish_target_temp" not in st


@pytest.mark.asyncio
async def test_descartar_fb_removes_buttons_not_message(monkeypatch):
    uid = 555
    st = {}
    mock_state = MagicMock()
    mock_state.get_user_state.return_value = st
    monkeypatch.setattr(cb, "state_manager", mock_state)

    update = MagicMock()
    query = MagicMock()
    query.data = "descartar_fb"
    # message.delete should NOT be called
    query.message.delete = AsyncMock()
    # instead we expect edit_message_reply_markup to be called
    query.edit_message_reply_markup = AsyncMock()
    query.answer = AsyncMock()
    query.message.text = "preview"
    update.callback_query = query
    update.effective_user.id = uid

    context = MagicMock()

    await cb.button_handler(update, context)

    assert query.edit_message_reply_markup.called
    assert not query.message.delete.called
