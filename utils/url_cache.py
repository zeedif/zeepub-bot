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
            is_valid BOOLEAN DEFAULT 1
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

# Inicializar BD al importar el módulo
init_db()
