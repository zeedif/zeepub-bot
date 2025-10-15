# core/state_manager.py
from typing import Dict, Any
from config.config_settings import config

class StateManager:
    """Manages user state for the bot"""
    
    def __init__(self):
        self.user_state: Dict[int, Dict[str, Any]] = {}
    
    def ensure_user(self, uid: int) -> Dict[str, Any]:
        """Ensure a user exists in state, create if not"""
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
                "opds_root_base": config.OPDS_ROOT_START
            }
        return self.user_state[uid]
    
    def get_user_state(self, uid: int) -> Dict[str, Any]:
        """Get user state, ensuring user exists"""
        return self.ensure_user(uid)
    
    def update_user_state(self, uid: int, updates: Dict[str, Any]):
        """Update specific fields in user state"""
        self.ensure_user(uid)
        self.user_state[uid].update(updates)
    
    def reset_user_state(self, uid: int):
        """Reset user state to initial values"""
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
            "msg_que_hacer": None
        }
    
    def clear_user_flags(self, uid: int):
        """Clear waiting flags for a user"""
        self.ensure_user(uid)
        self.user_state[uid].update({
            "esperando_destino_manual": False,
            "esperando_busqueda": False,
            "esperando_password": False
        })

# Global state manager instance
state_manager = StateManager()