# config/config_settings.py

import os
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Set
from dotenv import load_dotenv

load_dotenv()

@dataclass
class BotConfig:
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    
    # Dominio público (ej: zp-dev.sp-core.xyz o zeepub-bot.sp-core.xyz)
    PUBLIC_DOMAIN: str = os.getenv("PUBLIC_DOMAIN", "")
    
    # Si no se define BASE_URL, se construye usando PUBLIC_DOMAIN
    BASE_URL: str = os.getenv("BASE_URL", "")
    
    # URL base del servidor OPDS (ej: https://apps.tailfe99c.ts.net)
    OPDS_SERVER_URL: str = os.getenv("OPDS_SERVER_URL", "")
    
    # URL de la Mini App (para botones y referencias)
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
    
    # Variables originales del .env (son los sufijos/rutas)
    OPDS_ROOT_START_SUFFIX: str = os.getenv("OPDS_ROOT_START", "")
    OPDS_ROOT_EVIL_SUFFIX: str = os.getenv("OPDS_ROOT_EVIL", "")
    
    SECRET_SEED: str = os.getenv("SECRET_SEED", "")

    # Administradores (no tienen descargas ilimitadas aquí)
    ADMIN_USERS: Set[int] = field(default_factory=lambda: {
        int(x.strip())
        for x in os.getenv("ADMIN_USERS", "").split(",")
        if x.strip().isdigit()
    })

    # Listas de usuarios con distintos niveles
    WHITELIST: Set[int] = field(default_factory=lambda: {
        int(x.strip())
        for x in os.getenv("WHITELIST", "").split(",")
        if x.strip().isdigit()
    })
    VIP_LIST: Set[int] = field(default_factory=lambda: {
        int(x.strip())
        for x in os.getenv("VIP_LIST", "").split(",")
        if x.strip().isdigit()
    })
    PREMIUM_LIST: Set[int] = field(default_factory=lambda: {
        int(x.strip())
        for x in os.getenv("PREMIUM_LIST", "").split(",")
        if x.strip().isdigit()
    })
    
    # Facebook Publishers
    FACEBOOK_PUBLISHERS: Set[int] = field(default_factory=lambda: {
        int(x.strip())
        for x in os.getenv("FACEBOOK_PUBLISHERS", "").split(",")
        if x.strip().isdigit()
    })
    
    # Facebook Credentials
    FACEBOOK_PAGE_ACCESS_TOKEN: str = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    FACEBOOK_GROUP_ID: str = os.getenv("FACEBOOK_GROUP_ID", "")
    
    # Domain for public downloads
    DL_DOMAIN: str = os.getenv("DL_DOMAIN", "dl.zeepubs.com")

    # Límites por hora
    MAX_DOWNLOADS_PER_DAY: int = int(os.getenv("MAX_DOWNLOADS_PER_DAY", "5"))
    WHITELIST_DOWNLOADS_PER_DAY: int = int(os.getenv("WHITELIST_DOWNLOADS_PER_DAY", "10"))
    VIP_DOWNLOADS_PER_DAY: int = int(os.getenv("VIP_DOWNLOADS_PER_DAY", "20"))

    # Otros ajustes
    MAX_IN_MEMORY_BYTES: int = int(os.getenv("MAX_IN_MEMORY_BYTES", "10485760"))
    DEFAULT_AIOHTTP_TIMEOUT: int = int(os.getenv("AIOHTTP_TIMEOUT", "60"))
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "20"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    ENABLE_PLUGINS: bool = os.getenv("ENABLE_PLUGINS", "true").lower() == "true"
    PLUGIN_DIRECTORY: str = os.getenv("PLUGIN_DIRECTORY", "plugins")


    @property
    def OPDS_ROOT_START(self) -> str:
        # Usa el servidor OPDS si está definido, sino usa BASE_URL (fallback)
        base = self.OPDS_SERVER_URL if self.OPDS_SERVER_URL else self.BASE_URL
        return f"{base}{self.OPDS_ROOT_START_SUFFIX}"

    @property
    def OPDS_ROOT_EVIL(self) -> str:
        base = self.OPDS_SERVER_URL if self.OPDS_SERVER_URL else self.BASE_URL
        return f"{base}{self.OPDS_ROOT_EVIL_SUFFIX}"

    def validate(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not self.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN")
            
        # Lógica para URLs dinámicas
        if not self.BASE_URL and self.PUBLIC_DOMAIN:
            self.BASE_URL = f"https://{self.PUBLIC_DOMAIN}"
            
        if not self.WEBAPP_URL and self.PUBLIC_DOMAIN:
            self.WEBAPP_URL = f"https://{self.PUBLIC_DOMAIN}"

        if not self.BASE_URL:
            errors.append("BASE_URL (or PUBLIC_DOMAIN)")
            
        # Validar que al menos tengamos los sufijos (usando los nombres del .env)
        if not self.OPDS_ROOT_START_SUFFIX:
            errors.append("OPDS_ROOT_START")
        if not self.OPDS_ROOT_EVIL_SUFFIX:
            errors.append("OPDS_ROOT_EVIL")
        if not self.SECRET_SEED:
            errors.append("SECRET_SEED")
        return (len(errors) == 0, errors)

    def get_six_hour_password(self) -> str:
        """
        Genera la contraseña de 8 caracteres para el modo 'evil',
        igual al script PowerShell:
          raw = f"{seed}{Year}-{Month}-{Day}-B{block}"
        """
        now = datetime.now()
        block = now.hour // 6
        # Sin guión tras el seed, para coincidir con PowerShell
        raw = f"{self.SECRET_SEED}{now.year}-{now.month}-{now.day}-B{block}"
        sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return sha[:8]

config = BotConfig()
