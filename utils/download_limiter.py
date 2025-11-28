# utils/download_limiter.py

from typing import Union
from config.config_settings import config
from core.state_manager import state_manager


def downloads_left(uid: int) -> Union[int, str]:
    """
    Devuelve el número de descargas restantes según el nivel de usuario:
    - PremiumList: ilimitadas
    - VIPList: 20 descargas diarias
    - WhiteList: 10 descargas diarias
    - Resto: MAX_DOWNLOADS_PER_DAY por defecto (p.ej. 5)
    """
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
    Incrementa el contador de descargas usadas en el estado del usuario.
    """
    st = state_manager.get_user_state(uid)
    st["downloads_used"] = st.get("downloads_used", 0) + 1
