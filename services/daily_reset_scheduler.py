import asyncio
import logging
from datetime import datetime, timedelta
from utils.download_limiter import reset_all_downloads

logger = logging.getLogger(__name__)


async def daily_reset_loop():
    """
    Loop infinito que espera hasta la próxima medianoche para resetear las descargas.
    """
    logger.info("Daily reset scheduler started")
    while True:
        try:
            now = datetime.now()
            # Calcular próxima medianoche
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            wait_seconds = (next_midnight - now).total_seconds()
            logger.info(f"Próximo reset de descargas en {wait_seconds:.0f} segundos ({next_midnight})")

            # Esperar hasta medianoche
            await asyncio.sleep(wait_seconds)

            # Ejecutar reset
            logger.info("Ejecutando reset diario de descargas...")
            reset_all_downloads()
            logger.info("Reset diario completado.")

            # Pequeña pausa para asegurar que no se ejecute dos veces en el mismo segundo (improbable pero seguro)
            await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Daily reset scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Error en daily_reset_loop: {e}", exc_info=True)
            # Esperar un poco antes de reintentar para evitar bucle rápido de errores
            await asyncio.sleep(60)


def start_daily_reset_scheduler(bot=None):
    """
    Inicia la tarea de reset diario en background.
    El argumento 'bot' se acepta para consistencia con otros schedulers, aunque no se usa aquí.
    """
    asyncio.create_task(daily_reset_loop())
    logger.info("Daily reset scheduler task created")
