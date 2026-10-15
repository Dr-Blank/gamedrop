import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import PriceSnapshot, Product, Store, StoreUrl


class _FakeAdapter:
    def __init__(self, available: bool, preorder: bool | None):
        self.available = available
        self.preorder = preorder

    async def fetch_products(self) -> list[dict]:
        variant = {
            "variant_id": "v1",
            "variant_title": "Default",
            "price": 1999.0,
            "compare_at_price": None,
            "available": self.available,
        }
        if self.preorder is not None:
            variant["preorder"] = self.preorder
        return [
            {
                "external_id": "e1",
                "title": "Catan",
                "handle": "catan",
                "url": "https://s1.com/products/catan",
                "variants": [variant],
            }
        ]


def _store(session: Session) -> Store:
    store = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(store)
    session.add(StoreUrl(store_id="s1", collection_path="/collections/board-games"))
    session.commit()
    return store


def _sync(session: Session, available=True, preorder=None) -> None:
    from app.scraper import sync_store

    store = session.get(Store, "s1")
    adapter = _FakeAdapter(available, preorder)
    with patch("app.scraper.get_adapter", return_value=adapter):
        asyncio.run(sync_store(store))


def _snapshots(session: Session) -> list[PriceSnapshot]:
    session.expire_all()
    return list(session.exec(select(PriceSnapshot).order_by(PriceSnapshot.recorded_at)))


def test_sync_records_preorder(session: Session):
    _store(session)
    _sync(session, preorder=True)
    assert [s.preorder for s in _snapshots(session)] == [True]


def test_adapters_without_preorder_default_to_false(session: Session):
    _store(session)
    _sync(session)
    assert [s.preorder for s in _snapshots(session)] == [False]


def test_preorder_flip_alone_is_a_new_reading(session: Session):
    _store(session)
    _sync(session, preorder=True)
    _sync(session, preorder=True)
    _sync(session, preorder=False)
    assert [s.preorder for s in _snapshots(session)] == [True, False]


def test_game_offer_reports_preorder(client: TestClient, session: Session):
    _store(session)
    _sync(session, preorder=True)
    game_id = session.exec(select(Product)).one().game_id

    offer = client.get(f"/api/games/{game_id}").json()["offers"][0]
    assert offer["available"] is True
    assert offer["preorder"] is True


def test_unavailable_offer_is_never_preorder(client: TestClient, session: Session):
    _store(session)
    _sync(session, available=False, preorder=True)
    game_id = session.exec(select(Product)).one().game_id

    offer = client.get(f"/api/games/{game_id}").json()["offers"][0]
    assert offer["preorder"] is False
