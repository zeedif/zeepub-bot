"""
Sistema de caché persistente para URLs acortadas usando SQLite.
"""
import sqlite3
import hashlib
import os
import time
from typing import Optional
import logging
from config.config_settings import config

# Optional SQLAlchemy support (for DATABASE_URL)
_HAS_SQLALCHEMY = False
try:
    import sqlalchemy as sa
    from sqlalchemy import Table, Column, String, Text, Integer, Boolean, MetaData, DateTime
    from sqlalchemy.exc import OperationalError, IntegrityError

    _HAS_SQLALCHEMY = True
except Exception:
    sa = None

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "url_cache.db")
# Use config override if provided (env var or default in config)
DB_PATH = config.URL_CACHE_DB_PATH or _DEFAULT_DB
if not os.path.isabs(DB_PATH):
    # Resolve relative to repository root (two levels up from utils/)
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), DB_PATH)

def _ensure_db_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _get_conn(retries: int = 3, timeout: float = 0.1) -> sqlite3.Connection:
    """Open a sqlite connection and apply recommended PRAGMA settings.

    Retries briefly when encountering SQLITE_BUSY/locked situations.
    """
    _ensure_db_dir()
    last_exc = None
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            # Improve durability/concurrency for WAL mode
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn
        except sqlite3.OperationalError as e:
            last_exc = e
            time.sleep(timeout)
            timeout *= 2
    # If we reach here, raise the last exception
    raise last_exc


def init_db():
    """Inicializa la base de datos SQLite y crea tablas si es necesario."""
    # If a DATABASE_URL is configured and SQLAlchemy is available, create the tables
    # through SQLAlchemy for portability; otherwise create the sqlite file/tables.
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        _init_with_sqlalchemy()
        return

    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS url_mappings (
                hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                book_title TEXT,
                series_name TEXT,
                volume_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                is_valid BOOLEAN DEFAULT 1,
                failed_checks INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        logger.info(f"URL cache database initialized at {DB_PATH}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _init_with_sqlalchemy():
    """Initialize DB schema using SQLAlchemy (used when DATABASE_URL provided)."""
    if not _HAS_SQLALCHEMY:
        raise RuntimeError("SQLAlchemy not available")

    engine = sa.create_engine(config.DATABASE_URL, future=True, pool_pre_ping=True)
    meta = MetaData()
    Table(
        "url_mappings",
        meta,
        Column("hash", String(128), primary_key=True),
        Column("url", Text, nullable=False),
        Column("book_title", Text),
        Column("series_name", Text),
        Column("volume_number", Text),
        Column("created_at", DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        Column("last_checked", DateTime),
        Column("is_valid", Boolean, server_default=sa.true()),
        Column("failed_checks", Integer, server_default="0"),
    )
    meta.create_all(engine)


def _get_sa_engine():
    if not _HAS_SQLALCHEMY:
        raise RuntimeError("SQLAlchemy not installed")
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    engine = sa.create_engine(config.DATABASE_URL, future=True, pool_pre_ping=True)
    return engine

def create_short_url(url: str, book_title: str = None, series_name: str = None, volume_number: str = None) -> str:
    """
    Crea un hash corto para una URL y lo guarda en la BD con metadata del libro.
    Si la URL ya existe, retorna el hash existente (deduplicación).
    Retorna el hash generado.
    """
    # If configured to use SQLAlchemy, use that backend
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        try:
            engine = _get_sa_engine()
            metadata = MetaData()
            url_mappings = Table('url_mappings', metadata, autoload_with=engine)

            full_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
            base_len = 12
            url_hash = full_hash[:base_len]

            # Use a connection/transaction to insert safely
            with engine.begin() as conn:
                # Check if URL already exists
                sel = sa.select(url_mappings.c.hash).where(url_mappings.c.url == url)
                r = conn.execute(sel).first()
                if r:
                    existing_hash = r[0]
                    if book_title:
                        upd = (
                            url_mappings.update()
                            .where(url_mappings.c.hash == existing_hash)
                            .values(book_title=book_title, series_name=series_name, volume_number=volume_number)
                        )
                        conn.execute(upd)
                    logger.debug(f"Reusing existing hash for URL: {existing_hash}")
                    return existing_hash

                attempt = 0
                while True:
                    try:
                        ins = url_mappings.insert().values(hash=url_hash, url=url, book_title=book_title, series_name=series_name, volume_number=volume_number, is_valid=True)
                        conn.execute(ins)
                        logger.debug(f"Created new URL mapping: {url_hash} -> {book_title or url[:50]}")
                        return url_hash
                    except IntegrityError:
                        # Collision: check if points to same URL
                        sel2 = sa.select(url_mappings.c.url).where(url_mappings.c.hash == url_hash)
                        r2 = conn.execute(sel2).first()
                        if r2 and r2[0] == url:
                            return url_hash
                        attempt += 1
                        if base_len + attempt <= len(full_hash):
                            url_hash = full_hash[: base_len + attempt ]
                            continue
                        # Last attempt: use full hash and replace
                        url_hash = full_hash
                        ins2 = sa.text("INSERT OR REPLACE INTO url_mappings (hash, url, book_title, series_name, volume_number, is_valid) VALUES (:h, :u, :bt, :sn, :vn, 1)")
                        conn.execute(ins2, {"h": url_hash, "u": url, "bt": book_title, "sn": series_name, "vn": volume_number})
                        return url_hash
        except Exception as e:
            logger.exception("SQLAlchemy create_short_url failed, falling back to sqlite: %s", e)
            # fall through to sqlite path

    # SQLite native path
    conn = _get_conn()
    try:
        cursor = conn.cursor()

        # Buscar si ya existe un hash para esta URL
        cursor.execute("SELECT hash, url FROM url_mappings WHERE url = ?", (url,))
        existing = cursor.fetchone()

        if existing:
            # Actualizar metadata si se proporciona
            if book_title:
                cursor.execute(
                    "UPDATE url_mappings SET book_title = ?, series_name = ?, volume_number = ? WHERE hash = ?",
                    (book_title, series_name, volume_number, existing[0])
                )
                conn.commit()
            logger.debug(f"Reusing existing hash for URL: {existing[0]}")
            return existing[0]

        # Si no existe, generar nuevo hash SHA256 (empezamos con 12 caracteres)
        full_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        base_len = 12
        url_hash = full_hash[:base_len]

        # Resolver colisiones (muy improbable) aumentando la longitud del hash
        attempt = 0
        while True:
            try:
                cursor.execute(
                    "INSERT INTO url_mappings (hash, url, book_title, series_name, volume_number, is_valid) VALUES (?, ?, ?, ?, ?, 1)",
                    (url_hash, url, book_title, series_name, volume_number)
                )
                conn.commit()
                logger.debug(f"Created new URL mapping: {url_hash} -> {book_title or url[:50]}")
                return url_hash
            except sqlite3.IntegrityError:
                # IntegrityError puede indicar que el hash ya existe en la tabla
                cursor.execute("SELECT url FROM url_mappings WHERE hash = ?", (url_hash,))
                row = cursor.fetchone()
                if row and row[0] == url:
                    # Otro proceso pudo haber insertado la misma URL
                    return url_hash
                # Si existía y apunta a otra URL, ampliar el hash y reintentar
                attempt += 1
                if base_len + attempt <= len(full_hash):
                    url_hash = full_hash[: base_len + attempt ]
                    continue
                # Como último recurso usar full hash (único)
                url_hash = full_hash
                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO url_mappings (hash, url, book_title, series_name, volume_number, is_valid) VALUES (?, ?, ?, ?, ?, 1)",
                        (url_hash, url, book_title, series_name, volume_number)
                    )
                    conn.commit()
                    return url_hash
                except Exception as e:
                    logger.error(f"Failed to insert url mapping after collision attempts: {e}")
                    return full_hash[:12]
    finally:
        try:
            conn.close()
        except Exception:
            pass

def get_url_from_hash(url_hash: str) -> Optional[str]:
    """
    Recupera la URL original desde el hash.
    Retorna None si no existe.
    """
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        with engine.connect() as conn:
            sel = sa.select(url_mappings.c.url).where(url_mappings.c.hash == url_hash)
            r = conn.execute(sel).first()
            if r:
                return r[0]
            return None

    conn = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM url_mappings WHERE hash = ?", (url_hash,))
        result = cursor.fetchone()

        if result:
            return result[0]
        return None
    except Exception as e:
        logger.error(f"Error retrieving URL: {e}")
        return None
    finally:
        conn.close()

def count_mappings() -> int:
    """Retorna el número total de mappings almacenados."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        with engine.connect() as conn:
            sel = sa.select(sa.func.count()).select_from(url_mappings)
            r = conn.execute(sel).scalar()
            return int(r or 0)

    conn = _get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM url_mappings")
        return cursor.fetchone()[0]
    finally:
        conn.close()

async def validate_and_update_url(url_hash: str, url: str) -> bool:
    """Valida una URL y actualiza su estado. Retorna True si es válida."""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            # Usar GET con range limitado en lugar de HEAD para mejor compatibilidad
            headers = {'Range': 'bytes=0-1024'}  # Solo descargar los primeros 1KB
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
                # Aceptar 200 (OK) o 206 (Partial Content)
                is_valid = 200 <= resp.status < 300
    except Exception as e:
        logger.debug("validate_and_update_url check failed for %s: %s", url_hash, e)
        is_valid = False
    
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        with engine.begin() as conn:
            if is_valid:
                upd = (
                    url_mappings.update()
                    .where(url_mappings.c.hash == url_hash)
                    .values(last_checked=sa.text("CURRENT_TIMESTAMP"), is_valid=True, failed_checks=0)
                )
                conn.execute(upd)
            else:
                upd = (
                    url_mappings.update()
                    .where(url_mappings.c.hash == url_hash)
                    .values(last_checked=sa.text("CURRENT_TIMESTAMP"), is_valid=False, failed_checks=url_mappings.c.failed_checks + 1)
                )
                conn.execute(upd)
        return is_valid

    conn = _get_conn()
    cursor = conn.cursor()

    try:
        if is_valid:
            # Restablecer contador de fallos
            cursor.execute(
                "UPDATE url_mappings SET last_checked = CURRENT_TIMESTAMP, is_valid = 1, failed_checks = 0 WHERE hash = ?",
                (url_hash,)
            )
        else:
            # Incrementar contador de fallos
            cursor.execute(
                "UPDATE url_mappings SET last_checked = CURRENT_TIMESTAMP, is_valid = 0, failed_checks = failed_checks + 1 WHERE hash = ?",
                (url_hash,)
            )
            
            # Borrar si alcanzó 3 fallos
                # Auto‑deletion after 3 fallos ha sido desactivada.
                # Se mantiene el registro para que el admin pueda revisarlo manualmente.
                # Si deseas volver a habilitar la eliminación automática, descomenta el bloque siguiente.
                # cursor.execute("SELECT failed_checks FROM url_mappings WHERE hash = ?", (url_hash,))
                # result = cursor.fetchone()
                # if result and result[0] >= 3:
                #     cursor.execute("DELETE FROM url_mappings WHERE hash = ?", (url_hash,))
                #     logger.warning(f"Deleted URL mapping {url_hash} after 3 failed checks")
        
        conn.commit()
    finally:
        conn.close()
    
    return is_valid

def get_stats() -> dict:
    """Retorna estadísticas de los links."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        with engine.connect() as conn:
            total = conn.execute(sa.select(sa.func.count()).select_from(url_mappings)).scalar() or 0
            valid = conn.execute(sa.select(sa.func.count()).select_from(url_mappings).where(url_mappings.c.is_valid == True)).scalar() or 0
            broken = conn.execute(sa.select(sa.func.count()).select_from(url_mappings).where(url_mappings.c.is_valid == False)).scalar() or 0
            at_risk = conn.execute(sa.select(sa.func.count()).select_from(url_mappings).where(url_mappings.c.failed_checks >= 2)).scalar() or 0
            return {"total": int(total), "valid": int(valid), "broken": int(broken), "at_risk": int(at_risk)}

    conn = _get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM url_mappings")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM url_mappings WHERE is_valid = 1")
        valid = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM url_mappings WHERE is_valid = 0")
        broken = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM url_mappings WHERE failed_checks >= 2")
        at_risk = cursor.fetchone()[0]

        return {
            "total": total,
            "valid": valid,
            "broken": broken,
            "at_risk": at_risk
        }
    finally:
        conn.close()

def get_broken_links(limit: int = 10):
    """Retorna lista de links rotos con su información."""
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        with engine.connect() as conn:
            sel = sa.select(url_mappings.c.hash, url_mappings.c.book_title, url_mappings.c.failed_checks, url_mappings.c.last_checked).where(url_mappings.c.is_valid == False).order_by(sa.desc(url_mappings.c.failed_checks), sa.desc(url_mappings.c.last_checked)).limit(limit)
            return list(conn.execute(sel).all())

    conn = _get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """SELECT hash, book_title, failed_checks, last_checked 
               FROM url_mappings 
               WHERE is_valid = 0 
               ORDER BY failed_checks DESC, last_checked DESC 
               LIMIT ?""",
            (limit,)
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_recent_links(limit: int = 20):
    """Return recent mappings as list of tuples (hash, url, book_title, created_at).

    Works with SQLAlchemy (DATABASE_URL) or fallback sqlite file.
    """
    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        sel = sa.select(url_mappings.c.hash, url_mappings.c.url, url_mappings.c.book_title, url_mappings.c.created_at).order_by(sa.desc(url_mappings.c.created_at)).limit(limit)
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(sel).all()]

    conn = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT hash, url, book_title, created_at
               FROM url_mappings
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,)
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_candidates_for_validation(limit: int = 100, older_than_seconds: int = 3600):
    """Return list of (hash, url) candidates that need validation.

    Criteria (sqlite path): last_checked IS NULL OR last_checked older than threshold
    or is_valid == 0.
    """
    from datetime import datetime, timedelta

    # Compute cutoff datetime in Python (UTC) so comparisons work in both SQLite and Postgres
    cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)

    if config.DATABASE_URL and _HAS_SQLALCHEMY:
        engine = _get_sa_engine()
        metadata = MetaData()
        url_mappings = Table('url_mappings', metadata, autoload_with=engine)
        from sqlalchemy import func
        with engine.connect() as conn:
            sel = sa.select(url_mappings.c.hash, url_mappings.c.url).where(
                sa.or_(url_mappings.c.last_checked == None,
                       url_mappings.c.last_checked < cutoff,
                       url_mappings.c.is_valid == False)
            ).limit(limit)
            return [tuple(r) for r in conn.execute(sel).all()]

    conn = _get_conn()
    cursor = conn.cursor()
    try:
        # Use a concrete cutoff string so it's portable across SQLite/Postgres
        cutoff_str = cutoff.isoformat(sep=' ', timespec='seconds')
        cursor.execute(
            """SELECT hash, url FROM url_mappings
               WHERE last_checked IS NULL OR last_checked < ?
                 OR is_valid = 0
               LIMIT ?""",
            (cutoff_str, limit)
        )
        return cursor.fetchall()
    finally:
        conn.close()

# Inicializar BD al importar el módulo
try:
    init_db()
except Exception as e:
    logger.error(f"Could not initialize URL cache DB at {DB_PATH}: {e}")
