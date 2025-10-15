import time
from config.config_settings import config

MAX_DOWNLOADS_PER_HOUR = getattr(config, "MAX_DOWNLOADS_PER_HOUR", 5)
DOWNLOAD_TIME_WINDOW = 3600  # segundos en una hora
DOWNLOAD_WHITELIST = getattr(config, "DOWNLOAD_WHITELIST", [])

user_download_limits = {}

def can_download(user_id: int) -> bool:
    if user_id in DOWNLOAD_WHITELIST:
        return True
    now = time.time()
    timestamps = user_download_limits.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < DOWNLOAD_TIME_WINDOW]
    if len(timestamps) >= MAX_DOWNLOADS_PER_HOUR:
        return False
    timestamps.append(now)
    user_download_limits[user_id] = timestamps
    return True

def downloads_left(user_id: int):
    if user_id in DOWNLOAD_WHITELIST:
        return "ilimitadas"
    now = time.time()
    timestamps = user_download_limits.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < DOWNLOAD_TIME_WINDOW]
    return MAX_DOWNLOADS_PER_HOUR - len(timestamps)
