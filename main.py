# main.py
import asyncio, logging
import nest_asyncio

from bot.app import build_app
from bot.config import settings
from bot.http import http_client

nest_asyncio.apply()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Iniciando HTTP client...")
    await http_client.startup()
    app = build_app()
    logger.info("Bot iniciado, entrando en polling...")
    try:
        await app.run_polling(stop_signals=None)
    finally:
        logger.info("Cerrando HTTP client...")
        await http_client.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Detenido por señal del sistema")
