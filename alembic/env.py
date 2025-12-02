from __future__ import with_statement
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# set the sqlalchemy.url to environment DATABASE_URL if provided
db_url = os.environ.get('DATABASE_URL')
if db_url:
    config.set_main_option('sqlalchemy.url', db_url)

# Define metadata directly to avoid circular imports
from sqlalchemy import MetaData, Table, Column, String, Text, Integer, Boolean, DateTime
meta = MetaData()
Table(
    "url_mappings",
    meta,
    Column("hash", String(128), primary_key=True),
    Column("url", Text, nullable=False),
    Column("book_title", Text),
    Column("series_name", Text),
    Column("volume_number", Text),
    Column("created_at", DateTime),
    Column("last_checked", DateTime),
    Column("is_valid", Boolean),
    Column("failed_checks", Integer),
)

target_metadata = meta

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Get DATABASE_URL from environment (already set in lines 16-18)
    db_url = config.get_main_option("sqlalchemy.url")
    
    from sqlalchemy import create_engine
    connectable = create_engine(db_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
