"""
Configuración centralizada del ZeePub Bot
Basado en las variables del bot original, adaptadas a la nueva arquitectura
"""

import os
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

@dataclass
class BotConfig:
    """Configuración centralizada del bot"""
    
    # ==== TELEGRAM SETTINGS ====
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    
    # ==== OPDS SETTINGS ====
    BASE_URL: str = os.getenv("BASE_URL", "")
    OPDS_ROOT_START_SUFFIX: str = os.getenv("OPDS_ROOT_START", "")
    OPDS_ROOT_EVIL_SUFFIX: str = os.getenv("OPDS_ROOT_EVIL", "")
    
    # ==== SECURITY ====
    SECRET_SEED: str = os.getenv("SECRET_SEED", "")
    
    # ==== ADMIN SETTINGS ====
    ADMIN_USERS: List[int] = field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("ADMIN_USERS", "").split(",") 
        if x.strip().isdigit()
    ])
    
    # ==== RATE LIMITING ====
    RATE_LIMIT_DOWNLOADS_PER_HOUR: int = int(os.getenv("RATE_LIMIT_DOWNLOADS", "10"))
    RATE_LIMIT_COMMANDS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_COMMANDS", "30"))
    RATE_LIMIT_SEARCHES_PER_HOUR: int = int(os.getenv("RATE_LIMIT_SEARCHES", "20"))
    
    # ==== PERFORMANCE SETTINGS ====
    MAX_IN_MEMORY_BYTES: int = int(os.getenv("MAX_IN_MEMORY_BYTES", "10485760"))  # 10MB
    DEFAULT_AIOHTTP_TIMEOUT: int = int(os.getenv("AIOHTTP_TIMEOUT", "60"))
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "20"))
    
    # ==== LOGGING ====
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # ==== PLUGIN SYSTEM ====
    PLUGIN_DIRECTORY: str = os.getenv("PLUGIN_DIRECTORY", "plugins")
    ENABLE_PLUGINS: bool = os.getenv("ENABLE_PLUGINS", "true").lower() == "true"
    
    # ==== COMPUTED PROPERTIES ====
    @property
    def OPDS_ROOT_START(self) -> str:
        """URL completa del OPDS root start"""
        return f"{self.BASE_URL}{self.OPDS_ROOT_START_SUFFIX}"
    
    @property
    def OPDS_ROOT_EVIL(self) -> str:
        """URL completa del OPDS root evil"""
        return f"{self.BASE_URL}{self.OPDS_ROOT_EVIL_SUFFIX}"
    
    def validate(self) -> tuple[bool, List[str]]:
        """
        Valida la configuración y retorna (es_valido, lista_errores)
        Basado en la validación original del bot
        """
        errors = []
        
        if not self.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN")
        if not self.BASE_URL:
            errors.append("BASE_URL")
        if not self.OPDS_ROOT_START_SUFFIX:
            errors.append("OPDS_ROOT_START")
        if not self.OPDS_ROOT_EVIL_SUFFIX:
            errors.append("OPDS_ROOT_EVIL")
        if not self.SECRET_SEED:
            errors.append("SECRET_SEED")
            
        return len(errors) == 0, errors
    
    def get_six_hour_password(self) -> str:
        """
        Genera password de 6 horas basado en SECRET_SEED
        Mantiene la lógica original del bot
        """
        now = datetime.now()
        bloque = now.hour // 6
        raw = f"{self.SECRET_SEED}-{now.year}-{now.month}-{now.day}-B{bloque}"
        return hashlib.sha256(raw.encode()).hexdigest()[:8]

# Instancia global de configuración
config = BotConfig()

# Validación al importar (como en el bot original)
if __name__ != "__main__":
    is_valid, missing = config.validate()
    if not is_valid:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(missing)}")

# Backward compatibility - mantener las constantes originales para facilitar migración
TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
BASE_URL = config.BASE_URL
OPDS_ROOT_START = config.OPDS_ROOT_START
OPDS_ROOT_EVIL = config.OPDS_ROOT_EVIL
SECRET_SEED = config.SECRET_SEED
MAX_IN_MEMORY_BYTES = config.MAX_IN_MEMORY_BYTES
DEFAULT_AIOHTTP_TIMEOUT = config.DEFAULT_AIOHTTP_TIMEOUT