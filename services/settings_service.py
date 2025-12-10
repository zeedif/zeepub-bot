"""
Servicio para gestionar configuración dinámica persistente (Key-Value).
Usa la misma base de datos que url_cache (SQLite o PostgreSQL).
"""

import sqlite3
import logging
import os
import time
from typing import Optional
from config.config_settings import config

# Optional SQLAlchemy support
_HAS_SQLALCHEMY = False
try:
    import sqlalchemy as sa
    from sqlalchemy import Table, Column, String, Text, MetaData
    _HAS_SQLALCHEMY = True
except Exception:
    sa = None

logger = logging.getLogger(__name__)

# Reusing the same DB path/configuration as url_cache
_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "url_cache.db"
)
DB_PATH = config.URL_CACHE_DB_PATH or _DEFAULT_DB
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), DB_PATH)


def _get_conn(retries: int = 3, timeout: float = 0.1) -> sqlite3.Connection:
    """Open a sqlite connection with retries."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    last_exc = None
    for _ in range(retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            return conn
        except sqlite3.OperationalError as e:
            last_exc = e
            time.sleep(timeout)
            timeout *= 2
    raise last_exc


def _get_sa_engine():
    if not _HAS_SQLALCHEMY:
        raise RuntimeError("SQLAlchemy not installed")
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    return sa.create_engine(config.DATABASE_URL, future=True, pool_pre_ping=True)


def init_settings_db():
    """Inicializa la tabla bot_settings."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        _init_with_sqlalchemy()
        return

    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _init_with_sqlalchemy():
    engine = _get_sa_engine()
    meta = MetaData()
    Table(
        "bot_settings",
        meta,
        Column("key", String(128), primary_key=True),
        Column("value", Text),
    )
    meta.create_all(engine)


def get_setting(key: str, default: str = None) -> Optional[str]:
    """Obtiene un valor de configuración."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        try:
            engine = _get_sa_engine()
            metadata = MetaData()
            settings = Table("bot_settings", metadata, autoload_with=engine)
            with engine.connect() as conn:
                sel = sa.select(settings.c.value).where(settings.c.key == key)
                result = conn.execute(sel).first()
                return result[0] if result else default
        except Exception as e:
            logger.error(f"Error getting setting {key} (SQLAlchemy): {e}")
            return default

    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default
    except Exception as e:
        logger.error(f"Error getting setting {key} (SQLite): {e}")
        return default
    finally:
        conn.close()


def set_setting(key: str, value: str):
    """Guarda o actualiza un valor de configuración."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        try:
            engine = _get_sa_engine()
            metadata = MetaData()
            settings = Table("bot_settings", metadata, autoload_with=engine)
            with engine.begin() as conn:
                # Upsert check
                sel = sa.select(settings.c.key).where(settings.c.key == key)
                if conn.execute(sel).first():
                    upd = (
                        settings.update()
                        .where(settings.c.key == key)
                        .values(value=str(value))
                    )
                    conn.execute(upd)
                else:
                    ins = settings.insert().values(key=key, value=str(value))
                    conn.execute(ins)
            return
        except Exception as e:
            logger.error(f"Error setting {key} (SQLAlchemy): {e}")

    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error setting {key} (SQLite): {e}")
    finally:
        conn.close()


# Inicializar al importar
try:
    init_settings_db()
except Exception as e:
    logger.error(f"Could not init settings DB: {e}")
