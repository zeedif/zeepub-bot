import uvicorn
import os

if __name__ == "__main__":
    from config.config_settings import config

    # Ejecutar uvicorn programáticamente
    # loop="asyncio" es necesario para compatibilidad con python-telegram-bot en algunos entornos
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        log_level=config.LOG_LEVEL.lower(),
    )
