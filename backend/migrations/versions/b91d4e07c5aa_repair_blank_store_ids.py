"""repair blank store ids and names

Stores added before the add-store form derived them could be saved with an empty
id or name. Blank values are filled from the store's URL and the rows that point
at the old id are repointed.

The derivation is duplicated here rather than imported from the app: a migration
has to keep behaving the same after the app's code moves on.

Revision ID: b91d4e07c5aa
Revises: cf8c412c034e
Create Date: 2026-08-10 23:40:00.000000

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b91d4e07c5aa"
down_revision: str | Sequence[str] | None = "cf8c412c034e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables holding a store_id that has to follow a renamed store.
REFERRING_TABLES = ("product", "synclog")

_HOST_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/:?#]+)")


def _derive_id(base_url: str) -> str:
    match = _HOST_RE.match((base_url or "").strip())
    label = match.group(1).split(".")[0] if match else ""
    return re.sub(r"[^a-z0-9-]", "-", label.lower()).strip("-")


def _derive_name(store_id: str) -> str:
    return " ".join(part.capitalize() for part in store_id.split("-") if part)


def _unique_id(candidate: str, taken: set[str]) -> str:
    base = candidate or "store"
    store_id = base
    suffix = 2
    while store_id in taken:
        store_id = f"{base}-{suffix}"
        suffix += 1
    return store_id


def upgrade() -> None:
    bind = op.get_bind()
    columns = [row[1] for row in bind.execute(sa.text("PRAGMA table_info(store)"))]
    if not columns:
        return

    taken = {
        row[0]
        for row in bind.execute(sa.text("SELECT id FROM store"))
        if (row[0] or "").strip()
    }

    blanks = (
        bind.execute(
            sa.text(
                "SELECT * FROM store"
                " WHERE TRIM(COALESCE(id, '')) = '' OR TRIM(COALESCE(name, '')) = ''"
            )
        )
        .mappings()
        .all()
    )

    for row in blanks:
        old_id = row["id"]
        new_id = (old_id or "").strip() or _unique_id(
            _derive_id(row["base_url"]), taken
        )
        new_name = (row["name"] or "").strip() or _derive_name(new_id)
        taken.add(new_id)

        if new_id == old_id:
            bind.execute(
                sa.text("UPDATE store SET name = :name WHERE id = :id"),
                {"name": new_name, "id": old_id},
            )
            continue

        # Insert under the new id, repoint the children, then drop the old row —
        # renaming a primary key in place breaks if foreign keys are enforced.
        values = dict(row)
        values["id"] = new_id
        values["name"] = new_name
        placeholders = ", ".join(f":{name}" for name in columns)
        bind.execute(
            sa.text(
                f"INSERT INTO store ({', '.join(columns)}) VALUES ({placeholders})"
            ),
            {name: values.get(name) for name in columns},
        )
        for table in REFERRING_TABLES:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET store_id = :new_id WHERE store_id = :old_id"
                ),
                {"new_id": new_id, "old_id": old_id},
            )
        bind.execute(
            sa.text("DELETE FROM store WHERE id = :old_id"), {"old_id": old_id}
        )


def downgrade() -> None:
    """Nothing to undo — blanking a store id back out would only break it."""
