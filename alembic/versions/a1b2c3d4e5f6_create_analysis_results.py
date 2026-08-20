"""create analysis_results table

Adds the table used to persist the LangGraph workflow output.

Revision ID: a1b2c3d4e5f6
Revises: f750290a7647
Create Date: 2026-08-20 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f750290a7647'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the analysis_results table."""

    op.create_table(
        'analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('score_explanation', sa.Text(), nullable=True),
        sa.Column('contract_data', sa.JSON(), nullable=True),
        sa.Column('llm_analysis', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
    )
    op.create_index('ix_analysis_results_id', 'analysis_results', ['id'])


def downgrade() -> None:
    """Drop the analysis_results table."""

    op.drop_index('ix_analysis_results_id', table_name='analysis_results')
    op.drop_table('analysis_results')