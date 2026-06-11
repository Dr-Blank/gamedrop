from datetime import datetime
from typing import Optional
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


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="store.id")
    external_id: str
    title: str
    handle: Optional[str] = None
    url: Optional[str] = None
    bgg_id: Optional[int] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        table_name = "product"


class PriceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    variant_id: Optional[str] = None
    variant_title: Optional[str] = None
    price: float
    compare_at_price: Optional[float] = None
    available: bool = True
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class BggCache(SQLModel, table=True):
    bgg_id: int = Field(primary_key=True)
    data: str  # JSON string
    cached_at: datetime = Field(default_factory=datetime.utcnow)


class WatchlistItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    target_price: Optional[float] = None
    last_notified_price: Optional[float] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """Key-value config store. UI values take priority over env vars."""
    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)
