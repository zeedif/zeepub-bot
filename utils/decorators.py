# utils/decorators.py
import os
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def cleanup_tmp(path):
    """Delete a temporary file if path is existing route."""
    if isinstance(path, str) and os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass

def rate_limit(max_calls: int = 5, period: int = 60):
    """Rate limiting decorator for bot functions"""
    call_times = {}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Simple rate limiting implementation
            # In production, you might want to use Redis or a more sophisticated approach
            import time
            now = time.time()
            
            # Extract user ID from args (assuming it's in update.effective_user.id)
            user_id = None
            for arg in args:
                if hasattr(arg, 'effective_user') and hasattr(arg.effective_user, 'id'):
                    user_id = arg.effective_user.id
                    break
            
            if user_id:
                if user_id not in call_times:
                    call_times[user_id] = []
                
                # Remove old calls outside the period
                call_times[user_id] = [t for t in call_times[user_id] if now - t < period]
                
                # Check if we've exceeded the limit
                if len(call_times[user_id]) >= max_calls:
                    logger.warning(f"Rate limit exceeded for user {user_id}")
                    return None
                
                # Add current call time
                call_times[user_id].append(now)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def handle_errors(error_message: str = "Ha ocurrido un error"):
    """Error handling decorator for bot functions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                
                # Try to send error message to user
                for arg in args:
                    if hasattr(arg, 'message') and hasattr(arg.message, 'reply_text'):
                        try:
                            await arg.message.reply_text(error_message)
                            break
                        except Exception:
                            pass
                    elif hasattr(arg, 'callback_query') and hasattr(arg.callback_query, 'edit_message_text'):
                        try:
                            await arg.callback_query.edit_message_text(error_message)
                            break
                        except Exception:
                            pass
                
                return None
        return wrapper
    return decorator

def require_state(func):
    """Decorator to ensure user state exists before executing function"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from core.state_manager import state_manager
        
        # Extract user ID from args
        user_id = None
        for arg in args:
            if hasattr(arg, 'effective_user') and hasattr(arg.effective_user, 'id'):
                user_id = arg.effective_user.id
                break
        
        if user_id:
            state_manager.ensure_user(user_id)
        
        return await func(*args, **kwargs)
    return wrapper