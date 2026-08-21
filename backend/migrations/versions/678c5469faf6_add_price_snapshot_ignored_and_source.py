"""add price snapshot ignored and source

Revision ID: 678c5469faf6
Revises: 7f2f87d80cc4
Create Date: 2026-08-20 20:00:51.109423

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "678c5469faf6"
down_revision: str | Sequence[str] | None = "7f2f87d80cc4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ignored", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default=sa.text("'scrape'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("pricesnapshot", schema=None) as batch_op:
        batch_op.drop_column("source")
        batch_op.drop_column("ignored")
