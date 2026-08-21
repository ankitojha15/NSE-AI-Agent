"""fix telegram dedup to use filing identity instead of content hash

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-20 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old unique constraint if present
    try:
        op.drop_constraint('uq_telegram_symbol_content', 'telegram_notifications', type_='unique')
    except Exception:
        pass
    # content_hash becomes nullable (kept for compat)
    try:
        op.alter_column('telegram_notifications', 'content_hash', existing_type=sa.String(length=64), nullable=True)
    except Exception:
        pass
    # Add filing_identity column
    try:
        op.add_column('telegram_notifications', sa.Column('filing_identity', sa.String(length=64), nullable=True))
    except Exception:
        pass
    # Backfill existing rows so the new column is not NULL
    conn = op.get_bind()
    try:
        conn.execute(sa.text("UPDATE telegram_notifications SET filing_identity = COALESCE(content_hash, 'migrated-' || id) WHERE filing_identity IS NULL"))
    except Exception:
        pass
    # Make it non-nullable and add unique constraint
    try:
        op.alter_column('telegram_notifications', 'filing_identity', existing_type=sa.String(length=64), nullable=False)
    except Exception:
        pass
    try:
        op.create_unique_constraint('uq_telegram_symbol_filing', 'telegram_notifications', ['symbol', 'filing_identity'])
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_constraint('uq_telegram_symbol_filing', 'telegram_notifications', type_='unique')
    except Exception:
        pass
    try:
        op.drop_column('telegram_notifications', 'filing_identity')
    except Exception:
        pass
    try:
        op.alter_column('telegram_notifications', 'content_hash', existing_type=sa.String(length=64), nullable=False)
    except Exception:
        pass
    try:
        op.create_unique_constraint('uq_telegram_symbol_content', 'telegram_notifications', ['symbol', 'content_hash'])
    except Exception:
        pass
