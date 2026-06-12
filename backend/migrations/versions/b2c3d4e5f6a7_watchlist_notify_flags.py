"""watchlist notify flags

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watchlistitem",
        sa.Column(
            "notify_price_drop",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "watchlistitem",
        sa.Column(
            "notify_back_in_stock",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "watchlistitem",
        sa.Column(
            "notify_target_reached",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("watchlistitem", "notify_target_reached")
    op.drop_column("watchlistitem", "notify_back_in_stock")
    op.drop_column("watchlistitem", "notify_price_drop")
