"""add shelf hidden flag

Revision ID: 927dd94505e0
Revises: adda30f35926
Create Date: 2026-07-22 14:28:48.150922

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "927dd94505e0"
down_revision: str | Sequence[str] | None = "adda30f35926"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed dropping the legacy 'bgcache' table; that is
    # destructive and unrelated, so it is left in place.
    with op.batch_alter_table("shelf", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("shelf", schema=None) as batch_op:
        batch_op.drop_column("hidden")
