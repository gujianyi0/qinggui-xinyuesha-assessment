"""Persist original request facts for recovery and ruling authority."""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('runs', sa.Column('request_data', sa.JSON(), nullable=True))
    op.create_table('budget_grants',
                    sa.Column('id', sa.String(80), primary_key=True),
                    sa.Column('amount', sa.Float(), nullable=False),
                    sa.Column('charged', sa.Float(), nullable=False),
                    sa.Column('status', sa.String(24), nullable=False),
                    sa.Column('details', sa.JSON(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('settled_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_table('budget_grants')
    op.drop_column('runs', 'request_data')
