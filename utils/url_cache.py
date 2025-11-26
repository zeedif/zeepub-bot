"""
Sistema de caché persistente para URLs acortadas usando SQLite.
"""
import sqlite3
import hashlib
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "url_cache.db")

def init_db():
    """Inicializa la base de datos SQLite."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    logger.info(f"URL cache database initialized at {DB_PATH}")

def create_short_url(url: str, book_title: str = None, series_name: str = None, volume_number: str = None) -> str:
    """
    Crea un hash corto para una URL y lo guarda en la BD con metadata del libro.
    Si la URL ya existe, retorna el hash existente (deduplicación).
    Retorna el hash generado.
    """
    # Primero verificar si la URL ya existe
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Buscar si ya existe un hash para esta URL
        cursor.execute("SELECT hash FROM url_mappings WHERE url = ?", (url,))
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
        
        # Si no existe, generar nuevo hash SHA256 (10 primeros caracteres)
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()[:10]
        
        # Guardar en BD con metadata
        cursor.execute(
            """INSERT OR REPLACE INTO url_mappings 
               (hash, url, book_title, series_name, volume_number, is_valid) 
               VALUES (?, ?, ?, ?, ?, 1)""",
            (url_hash, url, book_title, series_name, volume_number)
        )
        conn.commit()
        logger.debug(f"Created new URL mapping: {url_hash} -> {book_title or url[:50]}")
        return url_hash
        
    except Exception as e:
        logger.error(f"Error saving URL mapping: {e}")
        # En caso de error, generar el hash de todos modos
        return hashlib.sha256(url.encode('utf-8')).hexdigest()[:10]
    finally:
        conn.close()

def get_url_from_hash(url_hash: str) -> Optional[str]:
    """
    Recupera la URL original desde el hash.
    Retorna None si no existe.
    """
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    except:
        is_valid = False
    
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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

# Inicializar BD al importar el módulo
init_db()
