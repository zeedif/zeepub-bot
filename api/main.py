from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.bot import ZeePubBot
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancia global del bot
bot = ZeePubBot()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Iniciar el bot
    logger.info("Iniciando ZeePub Bot junto con la API...")
    await bot.initialize()
    await bot.start_async()
    yield
    # Shutdown: Detener el bot
    logger.info("Deteniendo ZeePub Bot...")
    await bot.stop_async()

app = FastAPI(
    title="ZeePub Bot API",
    description="API Backend para ZeePub Mini App",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a la URL del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Importar rutas
from api.routes import router
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "ZeePub Bot API is running"}
