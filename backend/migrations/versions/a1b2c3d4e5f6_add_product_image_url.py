"""add product image_url

Revision ID: a1b2c3d4e5f6
Revises: 3017421721aa
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "3017421721aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "image_url")
