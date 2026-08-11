"""Row builders for tests. A listing always needs a game, so these pair them."""

from __future__ import annotations

from sqlmodel import Session

from app.models import Game, Product, Store, WatchlistItem


def make_store(session: Session, store_id: str = "s1", **kwargs) -> Store:
    store = Store(
        id=store_id,
        name=kwargs.pop("name", store_id.upper()),
        type=kwargs.pop("type", "shopify"),
        base_url=kwargs.pop("base_url", f"https://{store_id}.com"),
        **kwargs,
    )
    session.add(store)
    session.commit()
    return store


def make_product(
    session: Session,
    *,
    store_id: str = "s1",
    title: str = "Catan",
    external_id: str | None = None,
    game: Game | None = None,
    commit: bool = True,
    **kwargs,
) -> Product:
    """A listing and, unless one is given, the game it belongs to."""
    if game is None:
        game = Game(title=title, bgg_id=kwargs.pop("bgg_id", None))
        session.add(game)
        session.flush()
    else:
        kwargs.pop("bgg_id", None)
    product = Product(
        store_id=store_id,
        game_id=game.id,
        external_id=external_id or f"{store_id}-{title}",
        title=title,
        **kwargs,
    )
    session.add(product)
    if commit:
        session.commit()
        session.refresh(product)
    else:
        session.flush()
    return product


def watch(session: Session, product: Product, **kwargs) -> WatchlistItem:
    """Watch the game a listing belongs to."""
    item = WatchlistItem(game_id=product.game_id, **kwargs)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
