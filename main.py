#!/usr/bin/env python3
import logging
from config.config_settings import config
from core.bot import ZeePubBot

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Iniciando ZeePub Bot...")
    is_valid, missing = config.validate()
    if not is_valid:
        logger.error(f"Faltan variables de entorno: {', '.join(missing)}")
        return

    bot = ZeePubBot()
    bot.start()
    logger.info("Bot detenido.")

if __name__ == "__main__":
    main()
