"""add provider_used to analysis_results

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-08-21 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.add_column('analysis_results', sa.Column('provider_used', sa.String(length=20), nullable=True))
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_column('analysis_results', 'provider_used')
    except Exception:
        pass
