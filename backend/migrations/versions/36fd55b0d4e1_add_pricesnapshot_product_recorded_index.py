"""add pricesnapshot product recorded index

Revision ID: 36fd55b0d4e1
Revises: 72ed19362349
Create Date: 2026-10-15 12:43:59.144111

"""

from collections.abc import Sequence

from alembic import op

revision: str = "36fd55b0d4e1"
down_revision: str | Sequence[str] | None = "72ed19362349"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed dropping the legacy 'bgcache' table; that is
    # destructive and unrelated, so it is left in place.
    op.create_index(
        "ix_pricesnapshot_product_recorded",
        "pricesnapshot",
        ["product_id", "recorded_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pricesnapshot_product_recorded",
        table_name="pricesnapshot",
        if_exists=True,
    )
