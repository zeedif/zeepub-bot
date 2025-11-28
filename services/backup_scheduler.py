import asyncio
import logging
import os
from datetime import datetime, timedelta
from config.config_settings import config
from services.backup_service import generate_backup_file

logger = logging.getLogger(__name__)


async def send_daily_backups(bot):
    """Genera y envía el backup diario a los administradores."""
    filename = None
    try:
        logger.info("Iniciando generación de backup diario...")
        filename = await generate_backup_file()

        if not filename or not os.path.exists(filename):
            logger.error("No se generó el archivo de backup")
            return

        sent_count = 0
        # Enviar a todos los admins
        for admin_id in config.ADMIN_USERS:
            try:
                with open(filename, "rb") as f:
                    await bot.send_document(
                        chat_id=admin_id,
                        document=f,
                        filename=filename,
                        caption=f"📦 Backup Diario Automático\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    )
                sent_count += 1
                # Pequeña pausa para no saturar si hay muchos admins (raro)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error enviando backup a admin {admin_id}: {e}")

        logger.info(f"Backup diario enviado a {sent_count} administradores")

    except Exception as e:
        logger.error(f"Error en send_daily_backups: {e}", exc_info=True)
    finally:
        # Limpiar archivo
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                logger.debug(f"No se pudo eliminar backup temporal: {filename}")


async def daily_backup_scheduler(bot):
    """Tarea que ejecuta el backup diario a las 04:00 AM."""
    logger.info("Daily backup scheduler started")

    while True:
        try:
            now = datetime.now()

            # Programar para las 04:00 AM de mañana (o de hoy si es temprano)
            # Pero para simplificar, siempre buscamos el "próximo 04:00"
            next_run = now.replace(hour=4, minute=0, second=0, microsecond=0)

            if next_run <= now:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(
                f"Próximo backup diario programado para: {next_run.strftime('%Y-%m-%d %H:%M')}"
            )

            await asyncio.sleep(wait_seconds)

            # Ejecutar backup
            logger.info("Ejecutando backup diario programado")
            await send_daily_backups(bot)

        except Exception as e:
            logger.error(f"Error en daily_backup_scheduler: {e}", exc_info=True)
            await asyncio.sleep(3600)  # Reintentar en 1 hora si falla el loop


def start_backup_scheduler(bot):
    """Inicia el scheduler de backups diarios en background."""
    asyncio.create_task(daily_backup_scheduler(bot))
    logger.info("Daily backup scheduler task created")
