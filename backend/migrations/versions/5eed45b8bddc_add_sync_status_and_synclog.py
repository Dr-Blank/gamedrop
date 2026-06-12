"""add sync status and synclog

Revision ID: 5eed45b8bddc
Revises:
Create Date: 2026-06-12 09:17:29.895169

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5eed45b8bddc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synclog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("new_products", sa.Integer(), nullable=False),
        sa.Column("updated_products", sa.Integer(), nullable=False),
        sa.Column("price_changes", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("store", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scrape_config", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_error", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("store", schema=None) as batch_op:
        batch_op.drop_column("last_sync_error")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("scrape_config")

    op.drop_table("synclog")
