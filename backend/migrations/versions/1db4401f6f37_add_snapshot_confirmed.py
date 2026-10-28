"""add snapshot confirmed

Revision ID: 1db4401f6f37
Revises: 36fd55b0d4e1
Create Date: 2026-10-28 05:24:08.233676

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1db4401f6f37"
down_revision: str | Sequence[str] | None = "36fd55b0d4e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed dropping the legacy 'bgcache' table; that is
    # destructive and unrelated, so it is left in place.
    columns = sa.inspect(op.get_bind()).get_columns("pricesnapshot")
    if "confirmed" in {c["name"] for c in columns}:
        return
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "confirmed", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.drop_column("confirmed")
