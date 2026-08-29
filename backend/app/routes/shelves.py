import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, TypeAdapter
from sqlmodel import Session, select

from ..db import get_session
from ..filter_engine import FilterNode, SortSpec
from ..models import Shelf
from ..repositories import catalog as repo

#: Parses any saved node, not only the two the builder started with.
_FILTER_NODE = TypeAdapter(FilterNode)

router = APIRouter(prefix="/shelves", tags=["shelves"])


class ShelfCreate(BaseModel):
    name: str
    icon: str = "Layers"
    filters: FilterNode | None = None
    sorts: list[SortSpec] = []


class ShelfPatch(BaseModel):
    name: str | None = None
    icon: str | None = None
    position: int | None = None
    hidden: bool | None = None


class ShelfReorder(BaseModel):
    ids: list[int]


@router.get("/")
def list_shelves(session: Session = Depends(get_session)):
    """Every shelf, hidden ones included — the home page editor needs both."""
    return session.exec(select(Shelf).order_by(Shelf.position, Shelf.id)).all()


@router.post("/", status_code=201)
def create_shelf(body: ShelfCreate, session: Session = Depends(get_session)):
    position = session.exec(select(Shelf).order_by(Shelf.position.desc())).first()
    next_pos = (position.position + 1) if position else 0
    shelf = Shelf(
        name=body.name,
        icon=body.icon,
        filters=json.dumps(body.filters.model_dump()) if body.filters else None,
        sorts=json.dumps([s.model_dump() for s in body.sorts]) if body.sorts else None,
        built_in=False,
        position=next_pos,
    )
    session.add(shelf)
    session.commit()
    session.refresh(shelf)
    return shelf


@router.patch("/{shelf_id}")
def patch_shelf(
    shelf_id: int, body: ShelfPatch, session: Session = Depends(get_session)
):
    shelf = session.get(Shelf, shelf_id)
    if not shelf:
        raise HTTPException(404, "Shelf not found")
    if body.name is not None:
        shelf.name = body.name
    if body.icon is not None:
        shelf.icon = body.icon
    if body.position is not None:
        shelf.position = body.position
    if body.hidden is not None:
        shelf.hidden = body.hidden
    session.add(shelf)
    session.commit()
    session.refresh(shelf)
    return shelf


@router.post("/reorder")
def reorder_shelves(body: ShelfReorder, session: Session = Depends(get_session)):
    """Set shelf order from a list of ids. Shelves omitted from the list keep
    their relative order and land after the listed ones."""
    shelves = session.exec(select(Shelf).order_by(Shelf.position, Shelf.id)).all()
    by_id = {s.id: s for s in shelves}

    missing = [sid for sid in body.ids if sid not in by_id]
    if missing:
        raise HTTPException(404, f"Unknown shelf ids: {missing}")
    if len(set(body.ids)) != len(body.ids):
        raise HTTPException(400, "Duplicate shelf ids")

    ordered = [by_id[sid] for sid in body.ids]
    ordered += [s for s in shelves if s.id not in set(body.ids)]
    for pos, shelf in enumerate(ordered):
        shelf.position = pos
        session.add(shelf)
    session.commit()
    return session.exec(select(Shelf).order_by(Shelf.position, Shelf.id)).all()


@router.delete("/{shelf_id}", status_code=204)
def delete_shelf(shelf_id: int, session: Session = Depends(get_session)):
    shelf = session.get(Shelf, shelf_id)
    if not shelf:
        raise HTTPException(404, "Shelf not found")
    if shelf.built_in:
        raise HTTPException(403, "Cannot delete built-in shelf")
    session.delete(shelf)
    session.commit()


@router.get("/preview")
def shelves_preview(limit: int = 8, session: Session = Depends(get_session)):
    """Visible shelves with a product preview — single request for the home page."""
    shelves = session.exec(
        select(Shelf)
        .where(Shelf.hidden == False)  # noqa: E712
        .order_by(Shelf.position, Shelf.id)
    ).all()
    result = []
    for shelf in shelves:
        filter_node = None
        sorts = None
        if shelf.filters:
            with contextlib.suppress(Exception):
                filter_node = _FILTER_NODE.validate_python(json.loads(shelf.filters))
        if shelf.sorts:
            with contextlib.suppress(Exception):
                sorts = [SortSpec(**s) for s in json.loads(shelf.sorts)]
        try:
            rows = repo.query_products(
                session, filter_node=filter_node, sorts=sorts, limit=limit
            )
            items = repo.make_cards(session, rows)
        except Exception:
            items = []
        result.append({"shelf": shelf, "items": items})
    return result
