import os
import hashlib
import datetime
from dotenv import load_dotenv

class Config:
    """Configuration class for the bot"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Core configuration
        self.BASE_URL = os.getenv("BASE_URL")
        self.OPDS_ROOT_START_SUFFIX = os.getenv("OPDS_ROOT_START")
        self.OPDS_ROOT_EVIL_SUFFIX = os.getenv("OPDS_ROOT_EVIL")
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        self.SECRET_SEED = os.getenv("SECRET_SEED")

        # Derived URLs
        if self.BASE_URL and self.OPDS_ROOT_START_SUFFIX:
            self.OPDS_ROOT_START = f"{self.BASE_URL}{self.OPDS_ROOT_START_SUFFIX}"
        else:
            self.OPDS_ROOT_START = None
            
        if self.BASE_URL and self.OPDS_ROOT_EVIL_SUFFIX:
            self.OPDS_ROOT_EVIL = f"{self.BASE_URL}{self.OPDS_ROOT_EVIL_SUFFIX}"
        else:
            self.OPDS_ROOT_EVIL = None
        
        # HTTP settings
        self.MAX_IN_MEMORY_BYTES = 10 * 1024 * 1024  # 10 MB
        self.DEFAULT_AIOHTTP_TIMEOUT = 60  # seconds
        
        # Legacy Kavita API (not used but kept for compatibility)
        self.KAVITA_API_KEY = None

        # New variables for downloads limit
        self.MAX_DOWNLOADS_PER_HOUR = int(os.getenv("MAX_DOWNLOADS_PER_HOUR", "5"))
        
        download_whitelist_env = os.getenv("DOWNLOAD_WHITELIST", "")
        if download_whitelist_env:
            self.DOWNLOAD_WHITELIST = [int(uid.strip()) for uid in download_whitelist_env.split(",") if uid.strip().isdigit()]
        else:
            self.DOWNLOAD_WHITELIST = []
    
    def validate_critical_config(self):
        """Validate that all critical configuration is present"""
        missing = []
        
        if not self.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_TOKEN")
        if not self.BASE_URL:
            missing.append("BASE_URL")
        if not self.OPDS_ROOT_START_SUFFIX:
            missing.append("OPDS_ROOT_START")
        if not self.OPDS_ROOT_EVIL_SUFFIX:
            missing.append("OPDS_ROOT_EVIL")
        
        if missing:
            raise SystemExit(f"Faltan variables de entorno: {', '.join(missing)}")
    
    def get_six_hour_password(self):
        """Generate a password that changes every 6 hours"""
        if not self.SECRET_SEED:
            raise ValueError("SECRET_SEED no configurado")
            
        now = datetime.datetime.now()
        bloque = now.hour // 6
        raw = f"{self.SECRET_SEED}{now.year}-{now.month}-{now.day}-B{bloque}"
        return hashlib.sha256(raw.encode()).hexdigest()[:8]

# Create a global config instance
config = Config()
