# utils/download_limiter.py

import json
import os
import logging
from typing import Union, Dict
from config.config_settings import config
# from core.state_manager import state_manager (Moved to local scope)

logger = logging.getLogger(__name__)

# Archivo para persistencia de descargas diarias
DAILY_DOWNLOADS_FILE = os.path.join("data", "daily_downloads.json")


def load_downloads() -> None:
    """
    Carga los contadores de descarga desde el archivo JSON al iniciar el bot.
    """
    if not os.path.exists(DAILY_DOWNLOADS_FILE):
        return

    try:
        with open(DAILY_DOWNLOADS_FILE, "r") as f:
            data = json.load(f)

        count = 0
        for uid_str, downloads in data.items():
            try:
                uid = int(uid_str)
                from core.state_manager import state_manager
                st = state_manager.get_user_state(uid)
                st["downloads_used"] = downloads
                count += 1
            except ValueError:
                continue

        logger.info(f"Cargados contadores de descarga para {count} usuarios.")
    except Exception as e:
        logger.error(f"Error cargando daily_downloads.json: {e}")


def save_download(uid: int, count: int) -> None:
    """
    Guarda el contador de descargas de un usuario específico en el JSON.
    """
    try:
        # Cargar datos existentes
        data = {}
        if os.path.exists(DAILY_DOWNLOADS_FILE):
            try:
                with open(DAILY_DOWNLOADS_FILE, "r") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                pass  # Si está corrupto, empezamos de nuevo

        # Actualizar usuario
        data[str(uid)] = count

        # Guardar (asegurando que el directorio data existe)
        os.makedirs(os.path.dirname(DAILY_DOWNLOADS_FILE), exist_ok=True)
        with open(DAILY_DOWNLOADS_FILE, "w") as f:
            json.dump(data, f)

    except Exception as e:
        logger.error(f"Error guardando descarga para {uid}: {e}")


def reset_all_downloads() -> None:
    """
    Resetea todos los contadores de descarga en memoria y elimina el archivo de persistencia.
    Se llama diariamente a las 00:00.
    """
    # 1. Resetear en memoria (state_manager)
    # Nota: state_manager.user_state es un dict {uid: {state...}}
    # Iteramos sobre todos los usuarios cargados en memoria
    from core.state_manager import state_manager
    for uid, state in state_manager.user_state.items():
        if "downloads_used" in state:
            state["downloads_used"] = 0

    # 2. Eliminar archivo de persistencia
    if os.path.exists(DAILY_DOWNLOADS_FILE):
        try:
            os.remove(DAILY_DOWNLOADS_FILE)
            logger.info("Archivo de descargas diarias eliminado (reset diario).")
        except Exception as e:
            logger.error(f"Error eliminando daily_downloads.json: {e}")
    else:
        logger.info("No había archivo de descargas diarias para eliminar.")


def downloads_left(uid: int) -> Union[int, str]:
    """
    Devuelve el número de descargas restantes según el nivel de usuario:
    - PremiumList: ilimitadas
    - VIPList: 20 descargas diarias
    - WhiteList: 10 descargas diarias
    - Resto: MAX_DOWNLOADS_PER_DAY por defecto (p.ej. 5)
    """
    from core.state_manager import state_manager
    st = state_manager.get_user_state(uid)
    used = st.get("downloads_used", 0)

    if uid in config.PREMIUM_LIST:
        return "ilimitadas"

    if uid in config.VIP_LIST:
        max_dl = config.VIP_DOWNLOADS_PER_DAY  # p.ej. 20
    elif uid in config.WHITELIST:
        max_dl = config.WHITELIST_DOWNLOADS_PER_DAY  # p.ej. 10
    else:
        max_dl = config.MAX_DOWNLOADS_PER_DAY  # p.ej. 5

    remaining = max_dl - used
    return remaining if remaining > 0 else 0


def can_download(uid: int) -> bool:
    """
    Comprueba si el usuario aún puede descargar:
    - Siempre True para PremiumList
    - True si quedan descargas para VIPList, WhiteList o usuarios normales
    """
    left = downloads_left(uid)
    if left == "ilimitadas":
        return True
    return left > 0


def record_download(uid: int) -> None:
    """
    Incrementa el contador de descargas usadas en el estado del usuario
    y lo persiste en disco.
    """
    from core.state_manager import state_manager
    st = state_manager.get_user_state(uid)
    new_count = st.get("downloads_used", 0) + 1
    st["downloads_used"] = new_count

    # Persistir cambio
    save_download(uid, new_count)
