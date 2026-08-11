from datetime import datetime

from sqlmodel import Field, SQLModel


class Store(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    type: str  # "shopify" | "woocommerce"
    base_url: str
    collection_path: str = "/collections/board-games"
    enabled: bool = True
    # JSON: timeout_sec, request_delay_sec, sync_interval_hours
    scrape_config: str = (
        '{"timeout_sec":30,"request_delay_sec":1,"sync_interval_hours":6}'
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_synced_at: datetime | None = None
    last_sync_error: str | None = None


class Product(SQLModel, table=True):
    """One shop's listing of a game: its URL, its price history, its stock.

    Everything the user *decides* (watching, naming, BGG identity) lives on
    `Game` instead, so two shops selling one game share those decisions.
    """

    id: int | None = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="store.id")
    game_id: int = Field(foreign_key="game.id", index=True)
    external_id: str
    title: str  # as the shop lists it; Game.title is the name shown
    handle: str | None = None
    url: str | None = None
    image_url: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        table_name = "product"


class Game(SQLModel, table=True):
    """The game itself — one row per game, however many shops sell it.

    Every listing has one, so watching, renaming, hiding and BGG linking work
    the same whether a game is sold by one shop or five.
    """

    id: int | None = Field(default=None, primary_key=True)
    title: str
    bgg_id: int | None = None
    hidden: bool = Field(default=False)  # hide the game from every view
    note: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GameAlias(SQLModel, table=True):
    """A game id that was merged away, and the game it now points at.

    Kept so bookmarks, open tabs and old notification links resolve instead of
    404ing after a merge.
    """

    old_game_id: int = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MergeRejection(SQLModel, table=True):
    """A rejected merge suggestion. Ids stored low-first so the pair is one row."""

    product_a_id: int = Field(primary_key=True, foreign_key="product.id")
    product_b_id: int = Field(primary_key=True, foreign_key="product.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PriceSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    variant_id: str | None = None
    variant_title: str | None = None
    price: float
    compare_at_price: float | None = None
    available: bool = True
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class BggCache(SQLModel, table=True):
    bgg_id: int = Field(primary_key=True)
    data: str  # JSON string
    cached_at: datetime = Field(default_factory=datetime.utcnow)


class WatchlistItem(SQLModel, table=True):
    """A watched game. Alerts fire per listing, so every shop is reported."""

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    target_price: float | None = None
    active: bool = True
    notify_price_drop: bool = True
    notify_back_in_stock: bool = True
    notify_target_reached: bool = True
    notify_price_increase: bool = True
    notify_out_of_stock: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatchListingState(SQLModel, table=True):
    """Last price a watched game's listing was alerted about.

    Per listing, not per game: two shops can sit at the same price, and a drop
    at one of them is still news.
    """

    watch_id: int = Field(primary_key=True, foreign_key="watchlistitem.id")
    product_id: int = Field(primary_key=True, foreign_key="product.id")
    last_notified_price: float | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SyncLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="store.id")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    new_products: int = 0
    updated_products: int = 0
    price_changes: int = 0
    error: str | None = None


class ProductOverride(SQLModel, table=True):
    """Corrections to what one shop reports. Name, BGG link and notes are the
    game's, so only per-listing facts live here."""

    product_id: int = Field(primary_key=True, foreign_key="product.id")
    url: str | None = None
    override_price: float | None = None
    override_available: bool | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """Key-value config store. UI values take priority over env vars."""

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Shelf(SQLModel, table=True):
    """Named filter+sort preset. Built-ins seeded on startup; user shelves added freely."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    icon: str = "Layers"  # lucide icon name
    filters: str | None = None  # JSON FilterNode or null = no filter
    sorts: str | None = None  # JSON SortSpec[] or null = default sort
    built_in: bool = False
    position: int = 0
    # Hidden shelves stay defined but drop off the home page. Built-in shelves
    # can't be deleted, so this is how they get removed from the home page.
    hidden: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int | None = Field(default=None, foreign_key="product.id")
    game_id: int | None = Field(default=None, foreign_key="game.id")
    kind: str  # price_drop | back_in_stock | target_reached
    title: str
    message: str
    product_url: str | None = None
    read_at: datetime | None = None
    sent_at: datetime = Field(default_factory=datetime.utcnow)
