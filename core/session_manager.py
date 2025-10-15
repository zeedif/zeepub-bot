# core/session_manager.py
import asyncio
import aiohttp
import logging
from typing import Dict

class SessionManager:
    """Manages global aiohttp session and user publish locks"""
    
    def __init__(self):
        self._global_session = None
        self.publish_locks: Dict[int, asyncio.Lock] = {}
        self.logger = logging.getLogger(__name__)
    
    def get_session(self):
        """Get or create the global aiohttp session"""
        if self._global_session is None:
            from config.config_settings import config
            connector = aiohttp.TCPConnector(limit=20)
            timeout = aiohttp.ClientTimeout(total=config.DEFAULT_AIOHTTP_TIMEOUT)
            self._global_session = aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout
            )
        return self._global_session
    
    def get_publish_lock(self, uid: int) -> asyncio.Lock:
        """Get or create a publish lock for a user"""
        if uid not in self.publish_locks:
            self.publish_locks[uid] = asyncio.Lock()
        return self.publish_locks[uid]
    
    async def close(self):
        """Close the global session"""
        if self._global_session is not None:
            try:
                await self._global_session.close()
                self.logger.debug("Sesión aiohttp cerrada correctamente")
            except Exception as e:
                self.logger.error(f"Error cerrando sesión aiohttp: {e}")
            finally:
                self._global_session = None

# Global session manager instance
session_manager = SessionManager()