from abc import ABC, abstractmethod
from typing import Dict, Callable, List, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes

class BasePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    async def initialize(self, bot_instance) -> bool:
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        pass

    def get_commands(self) -> Dict[str, Callable]:
        return {}

    def get_callback_handlers(self) -> Dict[str, Callable]:
        return {}

    def get_message_handlers(self) -> List[Callable]:
        return []

    async def on_download_request(self, user_id: int, epub_url: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    async def on_download_complete(self, user_id: int, epub_url: str, success: bool) -> None:
        pass
