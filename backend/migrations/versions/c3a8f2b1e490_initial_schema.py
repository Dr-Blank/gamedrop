"""initial schema

Revision ID: c3a8f2b1e490
Revises:
Create Date: 2026-06-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a8f2b1e490"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column(
            "collection_path",
            sa.String(),
            nullable=False,
            server_default="/collections/board-games",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("handle", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("bgg_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pricesnapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.String(), nullable=True),
        sa.Column("variant_title", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("compare_at_price", sa.Float(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bgcache",
        sa.Column("bgg_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.String(), nullable=False),
        sa.Column("cached_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("bgg_id"),
    )
    op.create_table(
        "watchlistitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("last_notified_price", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "appsetting",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("appsetting")
    op.drop_table("watchlistitem")
    op.drop_table("bgcache")
    op.drop_table("pricesnapshot")
    op.drop_table("product")
    op.drop_table("store")
