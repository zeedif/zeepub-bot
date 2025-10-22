# core/state_manager.py

from typing import Dict, Any
from config.config_settings import config

class StateManager:
    """Gestión de estado por usuario en memoria."""

    def __init__(self):
        self.user_state: Dict[int, Dict[str, Any]] = {}

    def get_user_state(self, uid: int) -> Dict[str, Any]:
        if uid not in self.user_state:
            self.user_state[uid] = {
                "historial": [],
                "libros": {},
                "colecciones": {},
                "nav": {"prev": None, "next": None},
                "titulo": "📚 Todas las bibliotecas",
                "destino": None,
                "chat_origen": None,
                "esperando_destino_manual": False,
                "esperando_busqueda": False,
                "esperando_password": False,
                "ultima_pagina": None,
                "opds_root": config.OPDS_ROOT_START,
                "opds_root_base": config.OPDS_ROOT_START,
                "series_id": None,
                "volume_id": None,
                "msg_que_hacer": None,
            }
        return self.user_state[uid]

# Instancia global
state_manager = StateManager()
