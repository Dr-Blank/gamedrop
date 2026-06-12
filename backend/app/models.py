from datetime import datetime

from sqlmodel import Field, SQLModel


class Store(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    type: str  # "shopify" | "custom"
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
    id: int | None = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="store.id")
    external_id: str
    title: str
    handle: str | None = None
    url: str | None = None
    bgg_id: int | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        table_name = "product"


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
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    target_price: float | None = None
    last_notified_price: float | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    """User-supplied corrections for any product field. Wins over scraped data."""

    product_id: int = Field(primary_key=True, foreign_key="product.id")
    title: str | None = None
    url: str | None = None
    bgg_id: int | None = None
    override_price: float | None = None
    override_available: bool | None = None
    note: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """Key-value config store. UI values take priority over env vars."""

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)
