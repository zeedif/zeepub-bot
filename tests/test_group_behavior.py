import sys
from unittest.mock import MagicMock

# Mock modules to avoid circular dependencies and import errors
sys.modules["core"] = MagicMock()
sys.modules["core.bot"] = MagicMock()
sys.modules["core.state_manager"] = MagicMock()
sys.modules["core.session_manager"] = MagicMock()
sys.modules["handlers.command_handlers"] = MagicMock()
sys.modules["handlers.callback_handlers"] = MagicMock()
sys.modules["services"] = MagicMock()
sys.modules["services.opds_service"] = MagicMock()
sys.modules["utils"] = MagicMock()
sys.modules["utils.http_client"] = MagicMock()
sys.modules["utils.helpers"] = MagicMock()
sys.modules["config"] = MagicMock()
sys.modules["config.config_settings"] = MagicMock()

import pytest
from unittest.mock import AsyncMock

# Now we can import safely
# We need to import the function, but since we mocked everything, the import might fail if we are not careful.
# Actually, if we mock `handlers.message_handlers`, we can't test it.
# We want to import the REAL `handlers.message_handlers` but mock its dependencies.
# So we should NOT mock `handlers.message_handlers` in sys.modules.

# But `handlers/__init__.py` imports other handlers.
# So we need to mock `handlers.command_handlers` and `handlers.callback_handlers` (which we did).

from handlers.message_handlers import recibir_texto

@pytest.mark.asyncio
async def test_recibir_texto_group_chat_suppression():
    # Mock Update and Context
    update = MagicMock()
    context = MagicMock()
    
    # Setup effective user and chat
    update.effective_user.id = 123
    update.effective_chat.id = 456
    update.effective_chat.type = 'group' # Simulate group chat
    update.message.text = "some random text"
    
    with pytest.MonkeyPatch.context() as m:
        # Mock the state manager where it is used in message_handlers
        mock_state_manager = MagicMock()
        mock_state_manager.get_user_state.return_value = {} # Empty state
        
        # Patch the import in handlers.message_handlers
        m.setattr("handlers.message_handlers.state_manager", mock_state_manager)
        
        # Also need to mock config
        mock_config = MagicMock()
        mock_config.get_six_hour_password.return_value = "password"
        m.setattr("handlers.message_handlers.config", mock_config)

        # Mock context.bot.send_message
        context.bot.send_message = AsyncMock()
        
        # Run the handler
        await recibir_texto(update, context)
        
        # Assert that send_message was NOT called
        context.bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_recibir_texto_group_chat_with_active_state():
    # Mock Update and Context
    update = MagicMock()
    context = MagicMock()
    
    # Setup effective user and chat
    update.effective_user.id = 123
    update.effective_chat.id = 456
    update.effective_chat.type = 'group' # Simulate group chat
    update.message.text = "password" # Correct password text
    
    with pytest.MonkeyPatch.context() as m:
        # Mock the state manager to simulate active state
        mock_state_manager = MagicMock()
        # Simulate user waiting for password
        mock_state_manager.get_user_state.return_value = {"esperando_password": True} 
        
        # Patch the import in handlers.message_handlers
        m.setattr("handlers.message_handlers.state_manager", mock_state_manager)
        
        # Mock config
        mock_config = MagicMock()
        mock_config.get_six_hour_password.return_value = "password"
        m.setattr("handlers.message_handlers.config", mock_config)

        # Mock context.bot.send_message and edit_message_text
        context.bot.send_message = AsyncMock()
        context.bot.edit_message_text = AsyncMock()
        
        # Run the handler
        await recibir_texto(update, context)
        
        # Assert that response WAS sent, because user is interacting with the bot (password)
        # The bot should respond to direct interactions even in groups
        context.bot.send_message.assert_called()

@pytest.mark.asyncio
async def test_recibir_texto_private_chat_response():
    # Mock Update and Context
    update = MagicMock()
    context = MagicMock()
    
    # Setup effective user and chat
    update.effective_user.id = 123
    update.effective_chat.id = 456
    update.effective_chat.type = 'private' # Simulate private chat
    update.message.text = "some random text"
    
    with pytest.MonkeyPatch.context() as m:
        # Mock the state manager
        mock_state_manager = MagicMock()
        mock_state_manager.get_user_state.return_value = {} # Empty state
        
        # Patch the import in handlers.message_handlers
        m.setattr("handlers.message_handlers.state_manager", mock_state_manager)
        
        mock_config = MagicMock()
        mock_config.get_six_hour_password.return_value = "password"
        m.setattr("handlers.message_handlers.config", mock_config)
        
        # Mock context.bot.send_message
        context.bot.send_message = AsyncMock()
        
        # Run the handler
        await recibir_texto(update, context)
        
        # Assert that send_message WAS called
        context.bot.send_message.assert_called_once()
        args, kwargs = context.bot.send_message.call_args
        assert "Usa /start para comenzar" in kwargs.get('text', '')
