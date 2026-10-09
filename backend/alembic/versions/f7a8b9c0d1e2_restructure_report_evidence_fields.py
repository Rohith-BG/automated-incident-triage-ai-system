"""restructure_report_evidence_fields

Replace evidence_summary and model_used with structured evidence
columns: raw_logs, raw_metrics, observability_analysis, code_diffs,
past_resolutions.

Revision ID: f7a8b9c0d1e2
Revises: 8312e5affb53, a1b2c3d4e5f6
Create Date: 2026-10-05 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = ('8312e5affb53', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new structured evidence columns
    op.add_column(
        'root_cause_reports',
        sa.Column('raw_logs', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.add_column(
        'root_cause_reports',
        sa.Column('raw_metrics', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.add_column(
        'root_cause_reports',
        sa.Column(
            'observability_analysis',
            sa.String(length=4000),
            nullable=False,
            server_default='',
        ),
    )
    op.add_column(
        'root_cause_reports',
        sa.Column('code_diffs', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.add_column(
        'root_cause_reports',
        sa.Column('past_resolutions', sa.JSON(), nullable=False, server_default='[]'),
    )

    # Drop replaced columns
    op.drop_column('root_cause_reports', 'evidence_summary')
    op.drop_column('root_cause_reports', 'model_used')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add dropped columns
    op.add_column(
        'root_cause_reports',
        sa.Column(
            'evidence_summary',
            sa.String(length=4000),
            nullable=False,
            server_default='',
        ),
    )
    op.add_column(
        'root_cause_reports',
        sa.Column(
            'model_used',
            sa.String(length=100),
            nullable=False,
            server_default='',
        ),
    )

    # Drop new columns
    op.drop_column('root_cause_reports', 'past_resolutions')
    op.drop_column('root_cause_reports', 'code_diffs')
    op.drop_column('root_cause_reports', 'observability_analysis')
    op.drop_column('root_cause_reports', 'raw_metrics')
    op.drop_column('root_cause_reports', 'raw_logs')
