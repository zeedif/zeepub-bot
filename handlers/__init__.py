# Estado global y utilidades comunes para todos los handlers
from typing import Dict, Any
from config import OPDS_ROOT_START

user_state: Dict[int, Dict[str, Any]] = {}


def ensure_user(uid: int) -> Dict[str, Any]:
    if uid not in user_state:
        user_state[uid] = {
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
            "opds_root": OPDS_ROOT_START,
            "opds_root_base": OPDS_ROOT_START,
            "series_id": None,
            "volume_id": None,
            "msg_que_hacer": None
        }
    return user_state[uid]


# Reexportar handlers para __main__.py
from .start_and_auth import start, evil, cancel, recibir_texto  # noqa: E402
from .navigation import mostrar_colecciones, abrir_zeepubs, button_handler, volver  # noqa: E402
from .search import buscar_epub  # noqa: E402
from .publish import set_destino, publicar_libro  # noqa: E402