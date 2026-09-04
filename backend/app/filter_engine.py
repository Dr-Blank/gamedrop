"""
Dynamic filter and sort engine.

Fields are auto-discovered from SQLModel model annotations — if you add a new
column to Product or PriceSnapshot, it becomes filterable/sortable for free.
BGG and computed fields are registered manually since they come from JSON or
derived expressions.

Filter node JSON schema (discriminated on "type"):
  Condition: {"type":"condition","field":"price","op":"gte","value":30}
  Group:     {"type":"group","op":"and","conditions":[...]}

Sort schema:
  [{"field":"available","dir":"desc"},{"field":"price","dir":"asc"}]
"""

from __future__ import annotations

import operator
import re
import types
import typing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, not_, or_, select
from sqlmodel import SQLModel

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_STR_OPS = frozenset(
    {
        "eq",
        "ne",
        "contains",
        "starts_with",
        "ends_with",
        "in",
        "not_in",
        "is_null",
        "is_not_null",
    }
)
_NUM_OPS = frozenset(
    {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "is_not_null"}
)
_BOOL_OPS = frozenset({"eq", "is_null", "is_not_null"})
_DT_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "is_null", "is_not_null"})

_TYPE_OPS: dict[str, frozenset[str]] = {
    "str": _STR_OPS,
    "int": _NUM_OPS,
    "float": _NUM_OPS,
    "bool": _BOOL_OPS,
    "datetime": _DT_OPS,
}


def _infer_type(annotation: Any) -> str:
    """Map Python type annotation → filter type string."""
    origin = typing.get_origin(annotation)
    # Unwrap Optional[X] / X | None
    if origin is typing.Union or origin is getattr(types, "UnionType", None):
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        if non_none:
            return _infer_type(non_none[0])
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is str:
        return "str"
    if annotation is datetime:
        return "datetime"
    return "str"  # safe fallback


# ---------------------------------------------------------------------------
# Field registry
# ---------------------------------------------------------------------------


@dataclass
class FieldDef:
    expr: Any  # SQLAlchemy column/expression
    type: str  # "str" | "int" | "float" | "bool" | "datetime"
    label: str
    sortable: bool = True
    filterable: bool = True

    @property
    def allowed_ops(self) -> frozenset[str]:
        return _TYPE_OPS.get(self.type, _STR_OPS)


def auto_register_model(
    model_cls: type[SQLModel],
    *,
    skip: set[str] | None = None,
) -> dict[str, FieldDef]:
    """Scan SQLModel class fields and build FieldDefs from column expressions."""
    skip = skip or set()
    result: dict[str, FieldDef] = {}

    # Support both Pydantic v1 (__fields__) and v2 (model_fields)
    try:
        field_items = {k: v.annotation for k, v in model_cls.model_fields.items()}
    except AttributeError:
        field_items = {k: v.outer_type_ for k, v in model_cls.__fields__.items()}

    for name, annotation in field_items.items():
        if name in skip:
            continue
        col = getattr(model_cls, name, None)
        if col is None:
            continue
        py_type = _infer_type(annotation)
        result[name] = FieldDef(
            expr=col,
            type=py_type,
            label=name.replace("_", " ").title(),
        )
    return result


def build_field_registry(
    bgg_subq: Any,
    first_seen_subq: Any | None = None,
    prev_snap_subq: Any | None = None,
    watchlist_subq: Any | None = None,
    store_count_subq: Any | None = None,
    cart_subq: Any | None = None,
    owned_subq: Any | None = None,
) -> dict[str, FieldDef]:
    """Build the full field registry for a single query execution."""
    from .models import Game, PriceSnapshot, Product

    reg: dict[str, FieldDef] = {}

    # Auto: listing fields. `title` is skipped so the game's name wins below —
    # filtering on one shop's marketing title is never what's wanted.
    reg.update(auto_register_model(Product, skip={"id", "title"}))

    # Auto: game fields (title, bgg_id, hidden, note)
    reg.update(auto_register_model(Game, skip={"id", "created_at"}))

    # Auto: PriceSnapshot (latest) fields. `ignored` is skipped because the
    # latest reading is by definition one that counts.
    reg.update(
        auto_register_model(
            PriceSnapshot,
            skip={"id", "product_id", "ignored"},
        )
    )

    # BGG fields (from JSON subquery — manual because they're extracted expressions)
    _bgg_fields = {
        "bgg_rating": ("float", "BGG Rating"),
        "avg_rating": ("float", "Avg User Rating"),
        "avg_weight": ("float", "Complexity Weight"),
        "bgg_rank": ("int", "BGG Rank"),
    }
    bgg_col_map = {
        "bgg_rating": "bgg_rating",
        "avg_rating": "avg_rating",
        "avg_weight": "avg_weight",
        "bgg_rank": "rank",  # column in subquery is named "rank"
    }
    for fname, (ftype, label) in _bgg_fields.items():
        col_name = bgg_col_map[fname]
        try:
            col = bgg_subq.c[col_name]
        except KeyError:
            continue
        reg[fname] = FieldDef(expr=col, type=ftype, label=label)

    # Computed: discount_pct / discount_abs
    from sqlalchemy import case

    discount_pct = case(
        (
            (PriceSnapshot.compare_at_price > PriceSnapshot.price)
            & (PriceSnapshot.compare_at_price > 0),
            (PriceSnapshot.compare_at_price - PriceSnapshot.price)
            / PriceSnapshot.compare_at_price
            * 100,
        ),
        else_=0,
    )
    discount_abs = case(
        (
            PriceSnapshot.compare_at_price > PriceSnapshot.price,
            PriceSnapshot.compare_at_price - PriceSnapshot.price,
        ),
        else_=0,
    )
    reg["discount_pct"] = FieldDef(
        expr=discount_pct,
        type="float",
        label="Discount %",
        sortable=True,
        filterable=True,
    )
    reg["discount_abs"] = FieldDef(
        expr=discount_abs,
        type="float",
        label="Absolute Discount",
        sortable=True,
        filterable=True,
    )

    # first_seen (from first_seen subquery)
    if first_seen_subq is not None:
        reg["first_seen"] = FieldDef(
            expr=first_seen_subq.c.first_date,
            type="datetime",
            label="First Seen",
        )

    # prev_snap derived fields
    if prev_snap_subq is not None:
        price_change = case(
            (
                prev_snap_subq.c.prev_price.is_not(None),
                PriceSnapshot.price - prev_snap_subq.c.prev_price,
            ),
            else_=None,
        )
        reg["price_change"] = FieldDef(
            expr=price_change,
            type="float",
            label="Price Change (vs prev)",
        )

        # % change: positive = rose, negative = dropped, NULL = no prev snapshot
        price_pct_change = case(
            (
                prev_snap_subq.c.prev_price.is_not(None)
                & (prev_snap_subq.c.prev_price > 0),
                (PriceSnapshot.price - prev_snap_subq.c.prev_price)
                / prev_snap_subq.c.prev_price
                * 100,
            ),
            else_=None,
        )
        reg["price_pct_change"] = FieldDef(
            expr=price_pct_change,
            type="float",
            label="Price Change %",
        )

        # True only when product was unavailable in prev snapshot and is now available
        back_in_stock = case(
            (
                (PriceSnapshot.available == True)  # noqa: E712
                & (prev_snap_subq.c.prev_available == False),  # noqa: E712
                True,
            ),
            else_=False,
        )
        reg["back_in_stock"] = FieldDef(
            expr=back_in_stock,
            type="bool",
            label="Back in Stock",
        )

        # A listing's first reading is not a change, so this stays NULL until a
        # second one lands — which is what separates a change from an arrival.
        reg["last_change_at"] = FieldDef(
            expr=case(
                (prev_snap_subq.c.product_id.is_not(None), PriceSnapshot.recorded_at),
                else_=None,
            ),
            type="datetime",
            label="Last Changed",
        )

    # store_count: shops selling this game — 1 means it is merged with nothing
    if store_count_subq is not None:
        reg["store_count"] = FieldDef(
            expr=func.coalesce(store_count_subq.c.store_count, 1),
            type="int",
            label="Stores Selling It",
        )

    # is_watched: true if the listing's game is watched
    if watchlist_subq is not None:
        is_watched = case(
            (watchlist_subq.c.game_id.is_not(None), True),
            else_=False,
        )
        reg["is_watched"] = FieldDef(
            expr=is_watched,
            type="bool",
            label="In Watchlist",
        )

    # is_in_cart / is_owned: the buy queue, and what has already been bought
    if cart_subq is not None:
        reg["is_in_cart"] = FieldDef(
            expr=case((cart_subq.c.game_id.is_not(None), True), else_=False),
            type="bool",
            label="In Buy Queue",
        )
    if owned_subq is not None:
        reg["is_owned"] = FieldDef(
            expr=case((owned_subq.c.game_id.is_not(None), True), else_=False),
            type="bool",
            label="Already Bought",
        )

    # random: pseudo-random ordering (sort-only, not filterable)
    reg["random"] = FieldDef(
        expr=func.random(),
        type="str",
        label="Random",
        filterable=False,
        sortable=True,
    )

    return reg


def describe_fields(registry: dict[str, FieldDef]) -> list[dict]:
    """Introspection payload for GET /browse/fields."""
    return [
        {
            "name": name,
            "type": fd.type,
            "label": fd.label,
            "ops": sorted(fd.allowed_ops),
            "sortable": fd.sortable,
            "filterable": fd.filterable,
        }
        for name, fd in sorted(registry.items())
    ]


# ---------------------------------------------------------------------------
# Filter AST (Pydantic)
# ---------------------------------------------------------------------------


class Condition(BaseModel):
    type: Literal["condition"] = "condition"
    field: str
    op: str
    value: Any = None


_STORE_CMP_FUNCS: dict[str, Any] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}
_STORE_CMP_OPS = frozenset(_STORE_CMP_FUNCS)


class StoreCompare(BaseModel):
    """Compare a game's latest price at two stores by their difference.

    The op tests `price_a - price_b` against `value`, so the plain "A cheaper
    than B" case is op=lt with the default threshold of 0.
    """

    type: Literal["store_compare"] = "store_compare"
    store_a: str
    store_b: str
    op: str
    value: float = 0
    mode: Literal["abs", "pct"] = "abs"


class ChangeWindow(BaseModel):
    """Games with at least one price or stock change inside a time window.

    A window is one node rather than two conditions because two conditions
    would be free to match two different readings — one after `since`, another
    before `until` — and report a game that never changed inside the window.
    Bounds accept the same relative values as any other date filter, and
    `store_id` narrows the window to one shop's readings.
    """

    type: Literal["change_window"] = "change_window"
    since: str | None = None
    until: str | None = None
    store_id: str | None = None


class Group(BaseModel):
    type: Literal["group"] = "group"
    op: Literal["and", "or", "not"]
    conditions: list[FilterNode]


FilterNode = Annotated[
    Condition | Group | StoreCompare | ChangeWindow, Field(discriminator="type")
]

Group.model_rebuild()  # resolve forward ref


# ---------------------------------------------------------------------------
# Sort spec
# ---------------------------------------------------------------------------


class SortSpec(BaseModel):
    field: str
    dir: Literal["asc", "desc"] = "asc"


# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------


def filter_uses_field(
    node: Condition | Group | StoreCompare | ChangeWindow, field: str
) -> bool:
    """Return True if the filter tree references a specific field anywhere."""
    if isinstance(node, Condition):
        return node.field == field
    if isinstance(node, StoreCompare | ChangeWindow):
        return False
    return any(filter_uses_field(c, field) for c in node.conditions)


def apply_filter(
    node: Condition | Group | StoreCompare | ChangeWindow,
    registry: dict[str, FieldDef],
) -> Any:
    """Recursively convert a FilterNode into a SQLAlchemy WHERE clause."""
    if isinstance(node, Condition):
        return _apply_condition(node, registry)
    if isinstance(node, StoreCompare):
        return _apply_store_compare(node)
    if isinstance(node, ChangeWindow):
        return _apply_change_window(node)
    return _apply_group(node, registry)


def _apply_change_window(node: ChangeWindow) -> Any:
    """Game.id IN (games with a change recorded inside the window)."""
    from .models import Game, PriceSnapshot, Product
    from .snapshots import effective

    ranked = (
        select(
            PriceSnapshot.product_id,
            PriceSnapshot.recorded_at.label("recorded_at"),
            func.row_number()
            .over(
                partition_by=PriceSnapshot.product_id,
                order_by=PriceSnapshot.recorded_at.asc(),
            )
            .label("rn"),
        )
        .where(effective())
        .subquery()
    )
    since = _to_datetime(node.since) if node.since is not None else None
    until = _to_datetime(node.until) if node.until is not None else None
    # A range, not a sequence: given both, the earlier bound is the start.
    if since is not None and until is not None and since > until:
        since, until = until, since

    # A listing's first reading is an arrival, not a change.
    clauses = [ranked.c.rn > 1]
    if node.store_id is not None:
        clauses.append(Product.store_id == node.store_id)
    if since is not None:
        clauses.append(ranked.c.recorded_at >= since)
    if until is not None:
        clauses.append(ranked.c.recorded_at <= until)

    changed_games = (
        select(Product.game_id)
        .join(ranked, ranked.c.product_id == Product.id)
        .where(*clauses)
    )
    return Game.id.in_(changed_games)


def _apply_store_compare(node: StoreCompare) -> Any:
    """Game.id IN (games whose store_a − store_b latest price gap `op` `value`)."""
    cmp_func = _STORE_CMP_FUNCS.get(node.op)
    if cmp_func is None:
        raise ValueError(f"Unknown store_compare op: {node.op!r}")

    from .models import Game, PriceSnapshot, Product
    from .snapshots import effective

    latest = (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .where(effective())
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )
    per_store_stmt = (
        select(
            Product.game_id.label("game_id"),
            Product.store_id.label("store_id"),
            PriceSnapshot.price.label("price"),
        )
        .join(latest, Product.id == latest.c.product_id)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date)
            & effective(),
        )
    )
    a = per_store_stmt.subquery("store_a")
    b = per_store_stmt.subquery("store_b")

    clauses = [a.c.store_id == node.store_a, b.c.store_id == node.store_b]
    if node.mode == "pct":
        gap: Any = (a.c.price - b.c.price) / b.c.price * 100
        clauses.append(b.c.price > 0)  # percentage is undefined against a zero base
    else:
        gap = a.c.price - b.c.price
    clauses.append(cmp_func(gap, node.value))

    matching_games = (
        select(a.c.game_id).join(b, a.c.game_id == b.c.game_id).where(*clauses)
    )
    return Game.id.in_(matching_games)


_NO_VALUE_OPS = frozenset({"is_null", "is_not_null"})

_RELATIVE_RE = re.compile(r"^(?:now)?\s*([+-])\s*(\d+)\s*(mo|[mhdwy])$")
_RELATIVE_UNITS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "mo": timedelta(days=30),
    "y": timedelta(days=365),
}


def _relative_datetime(text: str) -> datetime | None:
    """Resolve `now`, `today` or an offset like `-7d`, or None if it is neither.

    Stored filters keep the offset rather than the date it once resolved to, so
    a saved "changed this week" shelf still means this week a month from now.
    Months and years are fixed 30- and 365-day spans.
    """
    key = text.strip().lower()
    now = datetime.now(UTC).replace(tzinfo=None)
    if key == "now":
        return now
    if key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    match = _RELATIVE_RE.match(key)
    if match is None:
        return None
    sign, amount, unit = match.groups()
    delta = _RELATIVE_UNITS[unit] * int(amount)
    return now + delta if sign == "+" else now - delta


def _to_datetime(value: Any) -> datetime:
    """Parse a filter value into a real datetime, relative offsets included.

    SQLite has no datetime type and compares the stored text, so a string bound
    as-is is matched against `YYYY-MM-DD HH:MM:SS.ffffff` character by
    character — a `T` separator or missing microseconds silently flips the
    result. Only a datetime object binds in the stored format.
    """
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        relative = _relative_datetime(text)
        if relative is not None:
            return relative
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as e:
            raise ValueError(f"Not a date or datetime: {value!r}") from e
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _apply_condition(cond: Condition, registry: dict[str, FieldDef]) -> Any:
    if cond.field not in registry:
        raise ValueError(f"Unknown filter field: {cond.field!r}")
    fd = registry[cond.field]
    if cond.op not in fd.allowed_ops:
        raise ValueError(
            f"Operator {cond.op!r} not allowed on {cond.field!r} (type={fd.type})"
        )

    expr = fd.expr
    v = cond.value
    if fd.type == "datetime" and cond.op not in _NO_VALUE_OPS:
        v = [_to_datetime(x) for x in v] if isinstance(v, list) else _to_datetime(v)

    match cond.op:
        case "eq":
            return expr == v
        case "ne":
            return expr != v
        case "gt":
            return expr > v
        case "gte":
            return expr >= v
        case "lt":
            return expr < v
        case "lte":
            return expr <= v
        case "contains":
            return expr.ilike(f"%{v}%")
        case "starts_with":
            return expr.ilike(f"{v}%")
        case "ends_with":
            return expr.ilike(f"%{v}")
        case "in":
            return expr.in_(v if isinstance(v, list) else [v])
        case "not_in":
            return expr.notin_(v if isinstance(v, list) else [v])
        case "is_null":
            return expr.is_(None)
        case "is_not_null":
            return expr.is_not(None)
        case _:
            raise ValueError(f"Unknown op: {cond.op!r}")


def _apply_group(group: Group, registry: dict[str, FieldDef]) -> Any:
    children = [apply_filter(c, registry) for c in group.conditions]
    match group.op:
        case "and":
            return and_(*children)
        case "or":
            return or_(*children)
        case "not":
            if len(children) != 1:
                raise ValueError("NOT group must have exactly 1 condition")
            return not_(children[0])
        case _:
            raise ValueError(f"Unknown group op: {group.op!r}")


# ---------------------------------------------------------------------------
# Apply sorts
# ---------------------------------------------------------------------------


def apply_sorts(stmt: Any, specs: list[SortSpec], registry: dict[str, FieldDef]) -> Any:
    """Apply priority multi-sort chain to statement."""
    for spec in specs:
        if spec.field not in registry:
            raise ValueError(f"Unknown sort field: {spec.field!r}")
        fd = registry[spec.field]
        if not fd.sortable:
            raise ValueError(f"Field {spec.field!r} is not sortable")
        if spec.field == "random":
            stmt = stmt.order_by(func.random())
        else:
            expr = fd.expr
            clause = (
                expr.desc().nulls_last()
                if spec.dir == "desc"
                else expr.asc().nulls_last()
            )
            stmt = stmt.order_by(clause)
    return stmt


# ---------------------------------------------------------------------------
# Browse query request body
# ---------------------------------------------------------------------------


class BrowseQuery(BaseModel):
    filters: FilterNode | None = None
    sorts: list[SortSpec] = []
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=48, ge=1, le=200)
    include_hidden: bool = False
    # Keep hidden games in the result but behind every visible one.
    hidden_last: bool = False
