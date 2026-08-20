"""create companies and financial_results tables

Baseline schema for the NSE AI Earnings Analysis Agent.

Revision ID: f750290a7647
Revises:
Create Date: 2026-08-06 15:28:26.467896
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f750290a7647'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full application schema."""

    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('isin', sa.String(length=20), nullable=True),
        sa.Column('listing_status', sa.Boolean(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('isin')
    )
    op.create_index('ix_companies_id', 'companies', ['id'])
    op.create_index(
        'ix_companies_symbol',
        'companies',
        ['symbol'],
        unique=True
    )

    op.create_table(
        'financial_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seq_number', sa.String(length=30), nullable=False),
        sa.Column('symbol', sa.String(length=30), nullable=True),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('filing_date', sa.String(length=50), nullable=True),
        sa.Column('period', sa.String(length=100), nullable=True),
        sa.Column('audited', sa.String(length=30), nullable=True),
        sa.Column('consolidated', sa.String(length=50), nullable=True),
        sa.Column('xbrl_url', sa.String(length=500), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('financial_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('seq_number')
    )
    op.create_index('ix_financial_results_id', 'financial_results', ['id'])
    op.create_index(
        'ix_financial_results_symbol',
        'financial_results',
        ['symbol']
    )


def downgrade() -> None:
    """Drop the full application schema."""

    op.drop_index(
        'ix_financial_results_symbol',
        table_name='financial_results'
    )
    op.drop_index('ix_financial_results_id', table_name='financial_results')
    op.drop_table('financial_results')

    op.drop_index('ix_companies_symbol', table_name='companies')
    op.drop_index('ix_companies_id', table_name='companies')
    op.drop_table('companies')