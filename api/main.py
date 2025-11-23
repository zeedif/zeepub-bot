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

# Estado de la aplicación para acceso desde rutas
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Iniciar el bot
    logger.info("Iniciando ZeePub Bot junto con la API...")
    await bot.initialize()
    await bot.start_async()
    # Guardar el bot en app_state para acceso desde rutas
    app_state['bot'] = bot.app.bot
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

@app.get("/api_health")
async def root():
    return {"message": "ZeePub Bot API is running"}

# Montar archivos estáticos del frontend
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Ruta al directorio de build del frontend
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zeepub-web", "dist")

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Si es una ruta de API, dejar que FastAPI la maneje (ya definidas arriba)
        if full_path.startswith("api"):
            return {"error": "Not found"}
        
        # Servir index.html para cualquier otra ruta (SPA routing)
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not built"}
else:
    print(f"Advertencia: No se encontró el directorio {frontend_dist}. El frontend no se servirá.")
