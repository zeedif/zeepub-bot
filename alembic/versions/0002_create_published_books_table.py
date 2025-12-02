"""create_published_books_table

Revision ID: 0002_create_published_books_table
Revises: 0001_create_url_mappings
Create Date: 2025-12-01 22:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002_create_published_books_table'
down_revision = '0001_create_url_mappings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'published_books',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('message_id', sa.Integer, nullable=True),
        sa.Column('channel_id', sa.BigInteger, nullable=True),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('author', sa.Text, nullable=True),
        sa.Column('series', sa.Text, nullable=True),
        sa.Column('volume', sa.Text, nullable=True),
        sa.Column('slug', sa.Text, nullable=True),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('file_unique_id', sa.Text, nullable=True),
        sa.Column('date_published', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    # Create index on slug for faster lookups
    op.create_index('ix_published_books_slug', 'published_books', ['slug'])


def downgrade():
    op.drop_index('ix_published_books_slug', table_name='published_books')
    op.drop_table('published_books')
