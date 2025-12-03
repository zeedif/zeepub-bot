import logging
import json
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy import Table, Column, Integer, String, Text, BigInteger, DateTime, MetaData
from config.config_settings import config
from utils.helpers import generar_slug_from_meta

logger = logging.getLogger(__name__)

# SQLAlchemy setup
_HAS_SQLALCHEMY = False
try:
    from sqlalchemy import create_engine
    _HAS_SQLALCHEMY = True
except ImportError:
    pass


def _get_engine():
    if not _HAS_SQLALCHEMY:
        raise RuntimeError("SQLAlchemy not installed")
    if not config.DATABASE_URL:
        # Fallback to local sqlite if no DATABASE_URL, similar to url_cache
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "url_cache.db")
        return create_engine(f"sqlite:///{db_path}", future=True)
    return create_engine(config.DATABASE_URL, future=True, pool_pre_ping=True)


def _get_table(engine):
    metadata = MetaData()
    table = Table(
        "published_books",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("message_id", Integer, nullable=True),
        Column("channel_id", BigInteger, nullable=True),
        Column("title", Text, nullable=True),
        Column("author", Text, nullable=True),
        Column("series", Text, nullable=True),
        Column("volume", Text, nullable=True),
        Column("slug", Text, nullable=True),
        Column("file_size", Integer, nullable=True),
        Column("file_unique_id", Text, nullable=True),
        Column("date_published", DateTime, default=datetime.utcnow),
        Column("maquetado_por", Text, nullable=True),
        Column("demografia", Text, nullable=True),
        Column("generos", Text, nullable=True),
        Column("ilustrador", Text, nullable=True),
        Column("traduccion", Text, nullable=True),
    )
    # Ensure table exists
    metadata.create_all(engine)
    return table


def log_published_book(
    meta: Dict[str, Any],
    message_id: int,
    channel_id: int,
    file_info: Dict[str, Any] = None
):
    """
    Logs a published book to the database.
    """
    if not _HAS_SQLALCHEMY:
        logger.error("SQLAlchemy not available, cannot log published book")
        return

    try:
        engine = _get_engine()
        table = _get_table(engine)

        slug = generar_slug_from_meta(meta)

        # Extract fields from meta
        title = meta.get("titulo_volumen") or meta.get("titulo")
        author = meta.get("autor") or (meta.get("autores")[0] if meta.get("autores") else None)
        series = meta.get("titulo_serie")
        volume = meta.get("volume_index")  # Might need adjustment based on meta structure

        # Extract extended metadata fields
        # Maquetado por: convert list to comma-separated string
        maquetadores = meta.get("maquetadores", [])
        maquetado_por = ", ".join(maquetadores) if isinstance(maquetadores, list) else maquetadores

        # Demografia: convert list to comma-separated string or take first element
        demografia_list = meta.get("demografia", [])
        if isinstance(demografia_list, list) and demografia_list:
            demografia = ", ".join(demografia_list)
        elif isinstance(demografia_list, str):
            demografia = demografia_list
        else:
            demografia = None

        # Generos: convert list to comma-separated string
        generos_list = meta.get("generos", [])
        if isinstance(generos_list, list) and generos_list:
            generos = ", ".join(generos_list)
        elif isinstance(generos_list, str):
            generos = generos_list
        else:
            generos = None

        # Ilustrador
        ilustrador = meta.get("ilustrador")

        # Traduccion: from 'traductor' field in metadata
        traduccion = meta.get("traductor")

        # Extract fields from file_info
        file_size = file_info.get("file_size") if file_info else None
        file_unique_id = file_info.get("file_unique_id") if file_info else None

        with engine.begin() as conn:
            ins = table.insert().values(
                message_id=message_id,
                channel_id=channel_id,
                title=title,
                author=author,
                series=series,
                volume=str(volume) if volume else None,
                slug=slug,
                file_size=file_size,
                file_unique_id=file_unique_id,
                date_published=datetime.utcnow(),
                maquetado_por=maquetado_por,
                demografia=demografia,
                generos=generos,
                ilustrador=ilustrador,
                traduccion=traduccion
            )
            conn.execute(ins)
            logger.info(f"Logged published book: {slug} (Msg ID: {message_id})")

    except Exception as e:
        logger.error(f"Error logging published book: {e}")


def process_history_json(file_path: str) -> Dict[str, int]:
    """
    Parses a Telegram export JSON file and imports books into the database.
    Returns stats: {'total': 0, 'imported': 0, 'errors': 0}
    """
    import re  # Import at top of function
    stats = {'total': 0, 'imported': 0, 'errors': 0}

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return stats

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON: {e}")
        return stats

    messages = data.get('messages', [])
    channel_id = data.get('id', 0)  # Export might have channel ID

    # If channel_id is string "channel123", extract number
    if isinstance(channel_id, str) and not channel_id.isdigit():
        # Try to find numeric part? Or just use 0 if not clear.
        pass

    engine = _get_engine()
    
    # Debug: Check tables
    from sqlalchemy import inspect
    try:
        insp = inspect(engine)
        logger.info(f"Existing tables before creation: {insp.get_table_names()}")
    except Exception as e:
        logger.error(f"Error inspecting tables: {e}")

    table = _get_table(engine)
    
    try:
        insp = inspect(engine)
        logger.info(f"Existing tables after creation: {insp.get_table_names()}")
    except Exception as e:
        logger.error(f"Error inspecting tables: {e}")

    logger.info(f"Processing {len(messages)} messages from export")
    # Log first message structure for debugging
    if messages:
        logger.debug(f"First message sample: {messages[0]}")

    with engine.connect() as conn:
        for msg in messages:
            if msg.get('type') != 'message':
                continue

            # Check if it has a file (epub)
            file_info = msg.get('file')  # Telegram export format varies
            # Usually 'file' key exists if it's a document
            # Or check 'media_type'

            # We are looking for messages with #slugs
            text_entities = msg.get('text_entities', [])
            text_content = ""

            # Reconstruct text and look for hashtags
            slug = None
            for entity in text_entities:
                if entity.get('type') == 'hashtag':
                    text = entity.get('text', '')
                    if text.startswith('#'):
                        slug = text[1:]
                if entity.get('type') == 'plain':
                    text_content += entity.get('text', '')

            # If plain text is a list in 'text' field (older exports?)
            if isinstance(msg.get('text'), list):
                # Join parts
                full_text = ""
                for part in msg['text']:
                    if isinstance(part, str):
                        full_text += part
                    elif isinstance(part, dict) and part.get('type') == 'hashtag':
                        slug = part.get('text')[1:]
                        full_text += part.get('text')
                text_content = full_text
            elif isinstance(msg.get('text'), str):
                text_content = msg['text']
                # Extract slug from text if not found yet
                if not slug:
                    match = re.search(r'#(\w+)', text_content)
                    if match:
                        slug = match.group(1)

            if not slug:
                # logger.debug(f"No slug found in message {msg.get('id')}, skipping")
                continue

            # It seems to be a book post
            stats['total'] += 1
            logger.info(f"Processing book with slug: {slug}")

            # Extract other metadata from text (heuristic)
            # "Epub de: Series ║ Collection ║ Title"
            # "📂 Title"

            title = "Unknown"
            author = None
            series = None
            maquetado_por = None
            demografia = None
            generos = None
            ilustrador = None
            traduccion = None

            # Skip synopsis messages explicitly
            if text_content.strip().startswith("Sinopsis") or "Sinopsis:" in text_content[:20]:
                logger.debug(f"Skipping synopsis message {msg_id}")
                continue

            # Try to parse title line
            lines = text_content.split('\n')
            for line in lines:
                if "Epub de:" in line:
                    parts = line.replace("Epub de:", "").split('║')
                    if len(parts) >= 1:
                        series = parts[0].strip()
                    if len(parts) >= 3:
                        title = parts[2].strip()
                    elif len(parts) == 1:
                        title = parts[0].strip()  # Fallback
                elif "║" in line: # Handle lines like "Series ║ Title" without "Epub de:"
                    parts = line.split('║')
                    if len(parts) >= 1:
                        series = parts[0].strip()
                    if len(parts) >= 2:
                        title = parts[1].strip()
                elif line.strip().startswith("📂"):
                    # 📂 Title
                    title = line.replace("📂", "").strip()
                elif line.strip().startswith("Autor:") or "Autor:" in line:
                    author = line.split("Autor:")[-1].strip()
                elif "Maquetado por:" in line:
                    # Extract hashtags after "Maquetado por:"
                    parts = line.split("Maquetado por:")[-1]
                    # Find hashtags in the rest of the line
                    hashtags = re.findall(r'#(\w+)', parts)
                    if hashtags:
                        maquetado_por = ", ".join(hashtags)
                elif "Demografía:" in line:
                    demografia = line.split("Demografía:")[-1].strip()
                elif "Géneros:" in line:
                    generos = line.split("Géneros:")[-1].strip()
                elif "Ilustrador:" in line:
                    ilustrador = line.split("Ilustrador:")[-1].strip()
                elif "Traducción:" in line:
                    traduccion = line.split("Traducción:")[-1].strip()

            # File info from export
            # Export usually has 'file' path relative to export, not file_unique_id
            # We might not have file_unique_id from export
            file_size = None
            file_unique_id = None
            volume = None
            
            if isinstance(file_info, dict):
                 # Try to get size if available (unlikely in standard export but possible)
                 pass

            msg_id = msg.get('id')
            date_str = msg.get('date')
            date_published = datetime.utcnow()
            if date_str:
                try:
                    date_published = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                except Exception:
                    pass

            if not author:
                # If no author found, but we have a slug and it's not a synopsis, 
                # assume it's a book and use "Desconocido"
                author = "Desconocido"
                logger.info(f"Message {msg_id} (slug: {slug}) has no author, defaulting to 'Desconocido'")

            try:
                # Use a transaction for each item so failures don't break the loop
                with conn.begin():
                    # Check if already exists
                    sel = sa.select(table.c.id).where(
                        sa.and_(
                            table.c.message_id == msg_id,
                            table.c.slug == slug
                        )
                    )
                    existing = conn.execute(sel).first()

                    if not existing:
                        ins = table.insert().values(
                            message_id=msg_id,
                            channel_id=channel_id,  # Might be inaccurate from export
                            title=title,
                            author=author,
                            series=series,
                            volume=str(volume) if volume else None,
                            slug=slug,
                            file_size=file_size,
                            file_unique_id=file_unique_id,
                            date_published=date_published,
                            maquetado_por=maquetado_por,
                            demografia=demografia,
                            generos=generos,
                            ilustrador=ilustrador,
                            traduccion=traduccion
                        )
                        conn.execute(ins)
                        stats['imported'] += 1
                        logger.debug(f"Successfully imported book: {slug}")
            except Exception as e:
                logger.error(f"Error importing msg {msg_id} (slug: {slug}): {e}", exc_info=True)
                stats['errors'] += 1

    logger.info(f"Import complete: {stats['imported']}/{stats['total']} books imported, {stats['errors']} errors")
    return stats

def get_latest_books(limit: int = 10, channel_id: Optional[int] = None) -> list:
    """
    Retrieves the last N published books from the database.
    
    Args:
        limit: Maximum number of books to return
        channel_id: Optional channel/chat ID to filter by
    
    Returns:
        List of book records
    """
    if not _HAS_SQLALCHEMY:
        return []

    try:
        engine = _get_engine()
        table = _get_table(engine)
        
        with engine.connect() as conn:
            sel = sa.select(
                table.c.title,
                table.c.author,
                table.c.series,
                table.c.slug,
                table.c.date_published,
                table.c.file_size,
                table.c.maquetado_por,
                table.c.demografia,
                table.c.generos,
                table.c.ilustrador,
                table.c.traduccion,
                table.c.channel_id
            ).order_by(table.c.date_published.desc())
            
            # Apply channel filter if provided
            if channel_id is not None:
                sel = sel.where(table.c.channel_id == channel_id)
            
            sel = sel.limit(limit)
            
            result = conn.execute(sel).fetchall()
            return result
    except Exception as e:
        logger.error(f"Error getting latest books: {e}")
        return []

def clear_history():
    """
    Deletes all records from the published_books table.
    """
    if not _HAS_SQLALCHEMY:
        return False

    try:
        engine = _get_engine()
        # table = _get_table(engine) # Not strictly needed if we use text SQL
        
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("DELETE FROM published_books"))
            print("DEBUG: clear_history executed DELETE FROM published_books")
            return True
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        print(f"DEBUG: Error clearing history: {e}")
        return False
