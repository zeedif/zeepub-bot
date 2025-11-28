"""Create url_mappings table

Revision ID: 0001_create_url_mappings
Revises: 
Create Date: 2025-11-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_create_url_mappings'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'url_mappings',
        sa.Column('hash', sa.String(128), primary_key=True),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('book_title', sa.Text),
        sa.Column('series_name', sa.Text),
        sa.Column('volume_number', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_checked', sa.DateTime),
        sa.Column('is_valid', sa.Boolean, server_default=sa.true()),
        sa.Column('failed_checks', sa.Integer, server_default='0'),
    )


def downgrade():
    op.drop_table('url_mappings')
