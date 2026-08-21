"""create telegram_notifications table

Adds the table used to prevent duplicate Telegram notifications for
the same analysis content.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-20 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the telegram_notifications table."""

    op.create_table(
        'telegram_notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=30), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'symbol',
            'content_hash',
            name='uq_telegram_symbol_content',
        ),
    )
    op.create_index(
        'ix_telegram_notifications_id',
        'telegram_notifications',
        ['id'],
    )
    op.create_index(
        'ix_telegram_notifications_symbol',
        'telegram_notifications',
        ['symbol'],
    )


def downgrade() -> None:
    """Drop the telegram_notifications table."""

    op.drop_index(
        'ix_telegram_notifications_symbol',
        table_name='telegram_notifications',
    )
    op.drop_index(
        'ix_telegram_notifications_id',
        table_name='telegram_notifications',
    )
    op.drop_table('telegram_notifications')