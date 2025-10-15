from abc import ABC, abstractmethod
from typing import Dict, Callable, List, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes


class BasePlugin(ABC):
    """
    Clase base para todos los plugins.
    Define la interfaz que deben implementar.
    """

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
        """
        Inicializa el plugin con la instancia del bot.
        Retorna True si fue exitoso.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Limpia recursos cuando se desactiva el plugin.
        """
        pass

    def get_commands(self) -> Dict[str, Callable]:
        """
        Retorna un diccionario con comandos y sus manejadores.
        """
        return {}

    def get_callback_handlers(self) -> Dict[str, Callable]:
        """
        Retorna un diccionario con patrones de callback y sus manejadores.
        """
        return {}

    def get_message_handlers(self) -> List[Callable]:
        """
        Retorna una lista de handlers para mensajes.
        """
        return []

    async def on_download_request(self, user_id: int, epub_url: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Hook llamado antes de procesar una descarga.
        Puede retornar datos adicionales para procesar.
        """
        return None

    async def on_download_complete(self, user_id: int, epub_url: str, success: bool) -> None:
        """
        Hook llamado después de procesar una descarga.
        """
        pass
