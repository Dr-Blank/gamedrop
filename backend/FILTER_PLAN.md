# GameDrop — Filter & Browse System

## Goals

1. **Powerful filter engine** — every field on every model filterable; new fields auto-ready by type.
2. **Complex queries** — AND / OR / NOT + arbitrary nesting.
3. **Priority multi-sort** — sort by availability, then price, then discount, etc.
4. **Shelves = saved filters** — home page shelves link to `/browse` with preset filter+sort JSON.
5. **Backward compat** — existing `GET /api/browse/` query params keep working.

---

## Filter Node Schema (JSON)

```jsonc
// Condition (leaf)
{ "type": "condition", "field": "price", "op": "gte", "value": 30.0 }

// Group (branch)
{
  "type": "group",
  "op": "and",           // "and" | "or" | "not"
  "conditions": [
    { "type": "condition", "field": "available", "op": "eq", "value": true },
    {
      "type": "group",
      "op": "or",
      "conditions": [
        { "type": "condition", "field": "store_id", "op": "eq", "value": "s1" },
        { "type": "condition", "field": "title", "op": "contains", "value": "catan" }
      ]
    }
  ]
}
```

### Operators by field type

| Type       | Operators                                                                 |
|------------|---------------------------------------------------------------------------|
| `str`      | eq, ne, contains, starts_with, ends_with, in, not_in, is_null, is_not_null |
| `int/float`| eq, ne, gt, gte, lt, lte, in, not_in, is_null, is_not_null               |
| `bool`     | eq, is_null, is_not_null                                                  |
| `datetime` | eq, ne, gt, gte, lt, lte, is_null, is_not_null                           |

---

## Sort Schema

```json
[
  { "field": "available", "dir": "desc" },
  { "field": "price",     "dir": "asc"  },
  { "field": "discount_pct", "dir": "desc" }
]
```

First item = primary sort; ties broken by next item, etc.

---

## Available Fields

Auto-discovered from SQLModel:

### Product
`id`, `store_id`, `external_id`, `title`, `handle`, `url`, `image_url`, `bgg_id`, `hidden`, `updated_at`

### PriceSnapshot (latest)
`price`, `compare_at_price`, `available`, `recorded_at`, `variant_id`, `variant_title`

### BGG (from JSON cache)
`bgg_rating`, `avg_rating`, `avg_weight`, `bgg_rank`

### Computed
`discount_pct` = (compare_at - price) / compare_at × 100  
`discount_abs` = compare_at - price  
`first_seen`   = earliest recorded_at for product

---

## API Endpoints

### Existing (backward compat)
```
GET /api/browse/?q=&store_id=&min_price=&max_price=&in_stock=&sort=&page=&limit=
```

### New
```
POST /api/browse/query
Body: { "filters": <FilterNode|null>, "sorts": <SortSpec[]>, "page": 1, "limit": 48 }
Returns: { "items": [...], "page": 1, "limit": 48, "total": 123 }

GET /api/browse/fields
Returns: [ { "name": "price", "type": "float", "label": "Price", "ops": [...], "sortable": true } ]
```

---

## Implementation

### `app/filter_engine.py` (new)
- `FieldDef` dataclass — expr + type + label + sortable
- `Condition` / `Group` Pydantic models (discriminated union on `type`)
- `SortSpec` Pydantic model
- `_infer_type(annotation)` — maps Python annotation → type string
- `auto_register_model(cls, prefix)` — scans `model_fields`, emits FieldDefs
- `build_field_registry(bgg_subq, first_seen_subq)` — full registry per query
- `apply_filter(node, registry)` → SQLAlchemy clause
- `apply_sorts(stmt, specs, registry)` → stmt with ORDER BY chain
- `describe_fields(registry)` → list[dict] for introspection endpoint

### `app/repositories/catalog.py` (updated)
- `query_products` accepts `filters: FilterNode | None` and `sorts: list[SortSpec] | None`
- `count_products` for total pagination count
- Legacy `CatalogFilters` path remains for backward compat via a translation layer

### `app/routes/browse.py` (updated)
- New `POST /query` + `GET /fields` endpoints
- Old `GET /` delegates to legacy path

---

## Shelf ↔ Filter Mapping (future UI, listed here for reference)

| Home shelf        | Equivalent filter+sort                                           |
|-------------------|------------------------------------------------------------------|
| Price drops       | `discount_pct > 0`, sort: discount_pct desc                     |
| New arrivals      | sort: first_seen desc                                            |
| Top discounts     | `compare_at_price > price`, sort: discount_pct desc             |
| In stock          | `available eq true`                                             |
| Watchlist         | (join watchlistitem — separate endpoint)                         |
| Random shelf      | sort: random (added as special sort key)                         |
