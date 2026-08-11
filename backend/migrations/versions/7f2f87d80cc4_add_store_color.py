"""add store color

Revision ID: 7f2f87d80cc4
Revises: 82039870f353
Create Date: 2026-08-11 12:14:58.201070

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f2f87d80cc4"
down_revision: str | Sequence[str] | None = "82039870f353"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("store", schema=None) as batch_op:
        batch_op.add_column(sa.Column("color", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("store", schema=None) as batch_op:
        batch_op.drop_column("color")
