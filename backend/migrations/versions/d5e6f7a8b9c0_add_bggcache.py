"""add bggcache table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    if "bggcache" not in inspect(bind).get_table_names():
        op.create_table(
            "bggcache",
            sa.Column("bgg_id", sa.Integer(), nullable=False),
            sa.Column("data", sa.String(), nullable=False),
            sa.Column("cached_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("bgg_id"),
        )


def downgrade() -> None:
    op.drop_table("bggcache")
