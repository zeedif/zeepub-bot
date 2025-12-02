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
    return Table(
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
    )


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
                date_published=datetime.utcnow()
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
    table = _get_table(engine)

    with engine.begin() as conn:
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
                continue

            # It seems to be a book post
            stats['total'] += 1

            # Extract other metadata from text (heuristic)
            # "Epub de: Series ║ Collection ║ Title"
            # "📂 Title"

            title = "Unknown"
            author = None
            series = None

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
                elif line.strip().startswith("📂"):
                    # 📂 Title
                    title = line.replace("📂", "").strip()
                elif line.strip().startswith("Autor:"):
                    author = line.replace("Autor:", "").strip()
                elif "Autor:" in line:  # bold html might be gone
                    pass

            # File info from export
            # Export usually has 'file' path relative to export, not file_unique_id
            # We might not have file_unique_id from export

            msg_id = msg.get('id')
            date_str = msg.get('date')
            date_published = datetime.utcnow()
            if date_str:
                try:
                    date_published = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                except Exception:
                    pass

            try:
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
                        slug=slug,
                        date_published=date_published
                    )
                    conn.execute(ins)
                    stats['imported'] += 1
            except Exception as e:
                logger.error(f"Error importing msg {msg_id}: {e}")
                stats['errors'] += 1

    return stats
