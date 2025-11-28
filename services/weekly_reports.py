"""
Servicio para enviar reportes semanales de links a publishers.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from config.config_settings import config

logger = logging.getLogger(__name__)


async def generate_weekly_report():
    """Genera el reporte semanal de links."""
    try:
        from utils.url_cache import get_stats, get_broken_links

        stats = get_stats()
        broken = get_broken_links(limit=10)

        success_rate = (
            (stats["valid"] / stats["total"] * 100) if stats["total"] > 0 else 0
        )

        report = f"📊 <b>Reporte Semanal de Links</b>\n\n"
        report += f"📈 <b>Estadísticas Generales:</b>\n"
        report += f"  • Total de links: {stats['total']}\n"
        report += f"  ✅ Válidos: {stats['valid']}\n"
        report += f"  ❌ Rotos: {stats['broken']}\n"
        report += f"  ⚠️ En riesgo: {stats['at_risk']} (2+ fallos)\n"
        report += f"  📈 Tasa de éxito: {success_rate:.1f}%\n\n"

        if broken:
            report += f"⚠️ <b>Links Rotos (máximo 10):</b>\n"
            for hash_val, title, failed, last_checked in broken:
                title_short = (
                    (title[:35] + "...")
                    if title and len(title) > 35
                    else (title or "Sin título")
                )
                report += f"  • {title_short}\n"
                report += f"    Hash: <code>{hash_val}</code> (Fallos: {failed}/3)\n"
            report += f"\n💡 Usa /purge_link <code>&lt;hash&gt;</code> para eliminar links rotos.\n"
        else:
            report += "✅ <b>No hay links rotos esta semana!</b>\n"

        report += f"\n📅 Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        return report
    except Exception as e:
        logger.error(f"Error generando reporte semanal: {e}", exc_info=True)
        return None


async def send_weekly_reports(bot):
    """Envía reportes semanales a todos los publishers."""
    try:
        report = await generate_weekly_report()
        if not report:
            logger.error("No se pudo generar el reporte semanal")
            return

        # Enviar a todos los publishers
        sent_count = 0
        for publisher_id in config.FACEBOOK_PUBLISHERS:
            try:
                await bot.send_message(
                    chat_id=publisher_id, text=report, parse_mode="HTML"
                )
                sent_count += 1
                logger.info(f"Reporte semanal enviado a publisher {publisher_id}")
            except Exception as e:
                logger.error(f"Error enviando reporte a publisher {publisher_id}: {e}")

        logger.info(f"Reportes semanales enviados a {sent_count} publishers")

    except Exception as e:
        logger.error(f"Error en send_weekly_reports: {e}", exc_info=True)


async def weekly_report_scheduler(bot):
    """Tarea que ejecuta los reportes semanales cada lunes a las 9:00 AM."""
    logger.info("Weekly report scheduler started")

    while True:
        try:
            # Calcular tiempo hasta el próximo lunes a las 9:00 AM
            now = datetime.now()

            # Encontrar el próximo lunes
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0 and now.hour >= 9:
                # Si hoy es lunes pero ya pasaron las 9 AM, esperar una semana
                days_until_monday = 7

            next_monday = now + timedelta(days=days_until_monday)
            next_run = next_monday.replace(hour=9, minute=0, second=0, microsecond=0)

            # Si el próximo lunes calculado ya pasó, añadir una semana
            if next_run <= now:
                next_run += timedelta(days=7)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(
                f"Próximo reporte semanal programado para: {next_run.strftime('%Y-%m-%d %H:%M')}"
            )

            # Esperar hasta la próxima ejecución
            await asyncio.sleep(wait_seconds)

            # Ejecutar el reporte
            logger.info("Ejecutando reporte semanal programado")
            await send_weekly_reports(bot)

        except Exception as e:
            logger.error(f"Error en weekly_report_scheduler: {e}", exc_info=True)
            # Esperar 1 hora antes de reintentar en caso de error
            await asyncio.sleep(3600)


def start_weekly_scheduler(bot):
    """Inicia el scheduler de reportes semanales en background."""
    asyncio.create_task(weekly_report_scheduler(bot))
    logger.info("Weekly scheduler task created")
