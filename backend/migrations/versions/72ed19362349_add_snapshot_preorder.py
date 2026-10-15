"""add snapshot preorder

Revision ID: 72ed19362349
Revises: d28c5a26e70a
Create Date: 2026-10-05 11:06:18.361954

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "72ed19362349"
down_revision: str | Sequence[str] | None = "d28c5a26e70a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "preorder", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.drop_column("preorder")
