"""add product overrides

Revision ID: 3017421721aa
Revises: 5eed45b8bddc
Create Date: 2026-06-12 09:42:19.179247

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3017421721aa"
down_revision: str | Sequence[str] | None = "5eed45b8bddc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "productoverride",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("bgg_id", sa.Integer(), nullable=True),
        sa.Column("override_price", sa.Float(), nullable=True),
        sa.Column("override_available", sa.Boolean(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("product_id"),
    )


def downgrade() -> None:
    op.drop_table("productoverride")
