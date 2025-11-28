import asyncio
import logging
from typing import Optional

from .url_cache import get_candidates_for_validation, validate_and_update_url

logger = logging.getLogger(__name__)

_validator_task: Optional[asyncio.Task] = None


async def _validator_loop(interval: int = 3600, batch_size: int = 50):
    logger.info(
        "URL validator started (interval=%s sec, batch=%s)", interval, batch_size
    )
    try:
        while True:
            try:
                candidates = get_candidates_for_validation(
                    limit=batch_size, older_than_seconds=interval
                )
                logger.debug("Validator found %d candidates", len(candidates))
                coros = []
                for url_hash, url in candidates:
                    coros.append(validate_and_update_url(url_hash, url))
                if coros:
                    results = await asyncio.gather(*coros, return_exceptions=True)
                    logger.debug("Validator run completed: %s", results)
            except Exception as e:
                logger.exception("Error during validator run: %s", e)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("URL validator stopped")
        raise


def start_background_validator(
    loop: Optional[asyncio.AbstractEventLoop] = None,
    interval: int = 3600,
    batch_size: int = 50,
):
    global _validator_task
    if _validator_task and not _validator_task.done():
        logger.debug("Validator already running")
        return _validator_task
    _loop = loop or asyncio.get_event_loop()
    _validator_task = _loop.create_task(
        _validator_loop(interval=interval, batch_size=batch_size)
    )
    return _validator_task


def stop_background_validator():
    global _validator_task
    if _validator_task and not _validator_task.done():
        _validator_task.cancel()
        _validator_task = None
