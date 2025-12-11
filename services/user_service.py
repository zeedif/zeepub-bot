import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, Union
from config.config_settings import config

# Optional SQLAlchemy support
_HAS_SQLALCHEMY = False
try:
    import sqlalchemy as sa
    from sqlalchemy import (
        Table,
        Column,
        Integer,
        String,
        DateTime,
        BigInteger,
        MetaData,
        text,
    )
    from sqlalchemy.engine import Engine

    _HAS_SQLALCHEMY = True
except Exception:
    sa = None

logger = logging.getLogger(__name__)

# Reusing the same DB path/configuration as url_cache/settings
_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "url_cache.db"
)
DB_PATH = config.URL_CACHE_DB_PATH or _DEFAULT_DB
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), DB_PATH)


def _get_engine():
    if _HAS_SQLALCHEMY and config.DATABASE_URL:
        return sa.create_engine(config.DATABASE_URL, future=True, pool_pre_ping=True)

    # Fallback to SQLite with SQLAlchemy if available, or just return None to signal manual SQLite
    if _HAS_SQLALCHEMY:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sa.create_engine(f"sqlite:///{DB_PATH}", future=True)
    return None


def get_sqlite_conn():
    import sqlite3

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_user_db():
    """Initializes the users table."""
    engine = _get_engine()
    if engine:
        msg = _init_with_sqlalchemy(engine)
        logger.info(f"User DB initialized (SQLAlchemy): {msg}")
    else:
        _init_sqlite_manual()
        logger.info("User DB initialized (Manual SQLite)")


def _init_with_sqlalchemy(engine: "Engine"):
    meta = MetaData()
    # Define table
    users_table = Table(
        "users",
        meta,
        Column("telegram_id", BigInteger, primary_key=True),
        Column(
            "role", String(50), nullable=False
        ),  # 'white', 'vip', 'premium', 'staff'
        Column("added_at", DateTime, default=datetime.utcnow),
        Column("expires_at", DateTime, nullable=True),
        Column("custom_status", String(100), nullable=True),
        Column("created_by", BigInteger, nullable=True),
    )
    meta.create_all(engine)
    return "Tables created or existing"


def _init_sqlite_manual():
    conn = get_sqlite_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                custom_status TEXT,
                created_by INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_user(
    telegram_id: int,
    role: str,
    duration_months: Optional[int] = None,
    custom_status: Optional[str] = None,
    created_by: Optional[int] = None,
):
    """
    Agrega o actualiza un usuario.
    Si duration_months es None y no existe, es 'infinito' (o controlado por logica de staff).
    Si duration_months se provee, se calcula expires_at = now + months.
    """
    expires_at = None
    if duration_months is not None:
        from datetime import timedelta
        import calendar

        # Simple approximation: 30 days * months
        # Or more precise:
        now = datetime.utcnow()
        # Add months logic roughly
        days = duration_months * 30
        expires_at = now + timedelta(days=days)

    engine = _get_engine()
    if engine:
        _upsert_sa(engine, telegram_id, role, expires_at, custom_status, created_by)
    else:
        _upsert_sqlite(telegram_id, role, expires_at, custom_status, created_by)


def _upsert_sa(engine, telegram_id, role, expires_at, custom_status, created_by):
    meta = MetaData()
    users = Table("users", meta, autoload_with=engine)

    with engine.begin() as conn:
        # Check if exists
        sel = sa.select(users.c.telegram_id).where(users.c.telegram_id == telegram_id)
        exists = conn.execute(sel).first()

        values = {"role": role, "created_by": created_by}
        if expires_at is not None:
            values["expires_at"] = expires_at
        if custom_status is not None:
            values["custom_status"] = custom_status

        if exists:
            # Update
            upd = (
                users.update()
                .where(users.c.telegram_id == telegram_id)
                .values(**values)
            )
            conn.execute(upd)
        else:
            # Insert
            values["telegram_id"] = telegram_id
            values["added_at"] = datetime.utcnow()
            # If not provided on update, make sure defaults are respectful (though nullable)
            if "expires_at" not in values:
                values["expires_at"] = None
            if "custom_status" not in values:
                values["custom_status"] = None

            ins = users.insert().values(**values)
            conn.execute(ins)


def _upsert_sqlite(telegram_id, role, expires_at, custom_status, created_by):
    conn = get_sqlite_conn()
    try:
        cursor = conn.cursor()
        # Check existence
        cursor.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        exists = cursor.fetchone()

        if exists:
            # Update fields dynamically
            fields = ["role = ?"]
            params = [role]
            if expires_at is not None:
                fields.append("expires_at = ?")
                params.append(expires_at)
            if custom_status is not None:
                fields.append("custom_status = ?")
                params.append(custom_status)
            if created_by is not None:
                fields.append("created_by = ?")
                params.append(created_by)

            params.append(telegram_id)
            sql = f"UPDATE users SET {', '.join(fields)} WHERE telegram_id = ?"
            cursor.execute(sql, tuple(params))
        else:
            cursor.execute(
                "INSERT INTO users (telegram_id, role, added_at, expires_at, custom_status, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    telegram_id,
                    role,
                    datetime.utcnow(),
                    expires_at,
                    custom_status,
                    created_by,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_user_info(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Retorna info del usuario desde DB: {role, expires_at, custom_status}.
    Retorna None si no existe en DB.
    """
    engine = _get_engine()
    if engine:
        return _get_user_sa(engine, telegram_id)
    else:
        return _get_user_sqlite(telegram_id)


def _get_user_sa(engine, telegram_id):
    meta = MetaData()
    users = Table("users", meta, autoload_with=engine)
    with engine.connect() as conn:
        sel = sa.select(users.c.role, users.c.expires_at, users.c.custom_status).where(
            users.c.telegram_id == telegram_id
        )
        row = conn.execute(sel).first()
        if row:
            return {"role": row[0], "expires_at": row[1], "custom_status": row[2]}
    return None


def _get_user_sqlite(telegram_id):
    conn = get_sqlite_conn()
    try:
        cursor = conn.cursor()
        # Sqlite stores datetime as string usually, might need parsing if read back raw
        cursor.execute(
            "SELECT role, expires_at, custom_status FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()
        if row:
            # Parse expires_at if string
            expires_at = row[1]
            if isinstance(expires_at, str) and expires_at:
                try:
                    # Generic parser or fixed format
                    from dateutil import parser

                    expires_at = parser.parse(expires_at)
                except ImportError:
                    # Fallback basic ISO
                    pass

            return {"role": row[0], "expires_at": expires_at, "custom_status": row[2]}
    finally:
        conn.close()
    return None


def remove_user(telegram_id: int):
    engine = _get_engine()
    if engine:
        meta = MetaData()
        users = Table("users", meta, autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(users.delete().where(users.c.telegram_id == telegram_id))
    else:
        conn = get_sqlite_conn()
        try:
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
        finally:
            conn.close()


# Auto-init on import
try:
    init_user_db()
except Exception as e:
    logger.error(f"Could not init user DB: {e}")


def get_effective_user(uid: int) -> Dict[str, Any]:
    """
    Determina el rol efectivo del usuario y estado, considerando DB y Config (legacy).
    Retorna un dict con keys: role, status_label, expires_at (puede ser None).
    Roles: 'admin', 'staff', 'premium', 'vip', 'white', 'free'.
    """
    # 1. Check DB
    info = get_user_info(uid)
    if info:
        # Check expiration
        expires_at = info.get("expires_at")
        if expires_at and expires_at < datetime.utcnow():
            # Expired
            return {
                "role": "free",
                "status_label": "Expirado",
                "expires_at": expires_at,
            }

        role = info.get("role", "free").lower()
        custom_status = info.get("custom_status")

        # Normalize DB roles to internal standards just in case
        return {
            "role": role,
            "status_label": custom_status or role.capitalize(),
            "expires_at": expires_at,
        }

    # 2. Legacy / Config Checks
    if uid in config.ADMIN_USERS:
        return {"role": "admin", "status_label": "Admin", "expires_at": None}

    # Facebook publishers could be considered Staff or Admin-like for some purposes,
    # but strictly speaking they are publishers. Let's map them to Staff for benefits?
    # The user asked for a specific "Staff" role.
    if uid in config.FACEBOOK_PUBLISHERS:
        return {"role": "staff", "status_label": "Publisher", "expires_at": None}

    if uid in config.PREMIUM_LIST:
        return {
            "role": "premium",
            "status_label": "Premium (Legacy)",
            "expires_at": None,
        }

    if uid in config.VIP_LIST:
        return {"role": "vip", "status_label": "VIP (Legacy)", "expires_at": None}

    if uid in config.WHITELIST:
        return {
            "role": "white",
            "status_label": "Patrocinador (Legacy)",
            "expires_at": None,
        }

    return {"role": "free", "status_label": "Lector", "expires_at": None}
