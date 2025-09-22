import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.DEBUG)

BASE_URL = os.getenv("BASE_URL")
OPDS_ROOT_START_SUFFIX = os.getenv("OPDS_ROOT_START")
OPDS_ROOT_EVIL_SUFFIX = os.getenv("OPDS_ROOT_EVIL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SECRET_SEED = os.getenv("SECRET_SEED")

missing = []
if not TELEGRAM_TOKEN:
    missing.append("TELEGRAM_TOKEN")
if not BASE_URL:
    missing.append("BASE_URL")
if not OPDS_ROOT_START_SUFFIX:
    missing.append("OPDS_ROOT_START")
if not OPDS_ROOT_EVIL_SUFFIX:
    missing.append("OPDS_ROOT_EVIL")
if not SECRET_SEED:
    missing.append("SECRET_SEED")
if missing:
    sys.exit(f"Faltan variables de entorno: {', '.join(missing)}")

OPDS_ROOT_START = f"{BASE_URL}{OPDS_ROOT_START_SUFFIX}"
OPDS_ROOT_EVIL = f"{BASE_URL}{OPDS_ROOT_EVIL_SUFFIX}"

# Configuración de aiohttp
DEFAULT_AIOHTTP_TIMEOUT = 60  # segundos por defecto para la sesión global
MAX_IN_MEMORY_BYTES = 10 * 1024 * 1024  # 10 MB threshold