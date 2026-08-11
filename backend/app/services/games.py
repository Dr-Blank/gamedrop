"""Games and the merging of shop listings into them.

Merges are never automatic: noisy store titles produce confident false
positives, so the engine only ranks candidates and the user confirms.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlmodel import Session, select

from ..logger import get_logger
from ..models import (
    Game,
    GameAlias,
    MergeRejection,
    NotificationLog,
    PriceSnapshot,
    Product,
    WatchListingState,
    WatchlistItem,
)
from ..repositories import catalog as repo
from ..text_search import MERGE_CUTOFF, match_key, rank_titles, similarity

log = get_logger(__name__)

SUGGESTION_LIMIT = 6

#: Tokens shared by more listings than this carry no identity, and blocking on
#: them makes the catalog-wide scan quadratic.
COMMON_TOKEN_LIMIT = 60


def _pair(a: int, b: int) -> tuple[int, int]:
    """Rejection key, low id first, so (a, b) and (b, a) are one row."""
    return (a, b) if a < b else (b, a)


def _rejected_with(session: Session, product_id: int) -> set[int]:
    """Listing ids rejected against this one."""
    rows = session.exec(
        select(MergeRejection).where(
            (MergeRejection.product_a_id == product_id)
            | (MergeRejection.product_b_id == product_id)
        )
    ).all()
    return {
        r.product_b_id if r.product_a_id == product_id else r.product_a_id for r in rows
    }


def _candidate_rows(session: Session, product: Product):
    """(listing id, game name, game id) for listings in other stores."""
    return session.exec(
        select(Product.id, Game.title, Product.game_id)
        .join(Game, Product.game_id == Game.id)
        .where(Product.store_id != product.store_id)
    ).all()


def suggestions_for(
    session: Session, product_id: int, limit: int = SUGGESTION_LIMIT
) -> list[dict]:
    """Ranked same-game candidates from other stores.

    Same-store matches are excluded: near-identical titles in one shop are
    usually different products, and they drown out the cross-store matches.
    """
    product = session.get(Product, product_id)
    if product is None:
        return []
    game = session.get(Game, product.game_id)
    if game is None:
        return []

    rejected = _rejected_with(session, product_id)
    key_tokens = set(match_key(game.title).split())

    scored: list[tuple[int, float]] = []
    seen_games: set[int] = set()
    for cand_id, cand_title, cand_game in _candidate_rows(session, product):
        if cand_id in rejected or cand_game == product.game_id:
            continue
        # Score only listings that share an identifying word.
        if key_tokens and not (key_tokens & set(match_key(cand_title).split())):
            continue
        score = similarity(game.title, cand_title)
        if score < MERGE_CUTOFF or cand_game in seen_games:
            continue
        seen_games.add(cand_game)
        scored.append((cand_id, score))

    scored.sort(key=lambda row: -row[1])
    return _suggestion_cards(session, scored[:limit])


def search_candidates(
    session: Session, product_id: int, query: str, limit: int = 12
) -> list[dict]:
    """Manual candidate search, for when the ranked suggestions miss.

    Same search the global bar uses, restricted to other stores' listings, with
    no score floor — the user typed the name, so their judgement is the filter.
    """
    product = session.get(Product, product_id)
    if product is None or not query.strip():
        return []

    rows = _candidate_rows(session, product)
    candidates = [
        (cand_id, title)
        for cand_id, title, cand_game in rows
        if cand_game != product.game_id
    ]
    ranked = rank_titles(query, candidates, limit=limit)
    return _suggestion_cards(
        session, ranked, rejected=_rejected_with(session, product_id)
    )


def _suggestion_cards(
    session: Session,
    scored: list[tuple[int, float]],
    *,
    rejected: set[int] | None = None,
) -> list[dict]:
    cards = repo.cards_by_ids(session, [pid for pid, _ in scored])
    by_id = {c["product"].id: c for c in cards}
    return [
        {
            "score": round(score, 1),
            "rejected": bool(rejected and pid in rejected),
            "item": by_id[pid],
        }
        for pid, score in scored
        if pid in by_id
    ]


def suggestion_queue(
    session: Session, limit: int = 20, min_score: float = MERGE_CUTOFF
) -> dict:
    """Catalog-wide merge candidates, best first, one decision per listing.

    A listing appears in at most one pair: a shop sells a given game once, so
    its best match is the only one worth deciding, and the rest would only be
    the same call asked again.
    """
    rows = session.exec(
        select(Product.id, Game.title, Product.store_id, Product.game_id)
        .join(Game, Product.game_id == Game.id)
        .where(Game.hidden == False)  # noqa: E712
    ).all()
    rejected = {
        (r.product_a_id, r.product_b_id) for r in session.exec(select(MergeRejection))
    }
    floor = max(min_score, MERGE_CUTOFF)

    by_token: dict[str, list[tuple]] = defaultdict(list)
    for row in rows:
        for token in set(match_key(row[1]).split()):
            by_token[token].append(row)

    best: dict[tuple[int, int], float] = {}
    for bucket in by_token.values():
        if len(bucket) < 2 or len(bucket) > COMMON_TOKEN_LIMIT:
            continue
        for i, (a_id, a_title, a_store, a_game) in enumerate(bucket):
            for b_id, b_title, b_store, b_game in bucket[i + 1 :]:
                if a_store == b_store or a_game == b_game:
                    continue
                key = _pair(a_id, b_id)
                if key in rejected or key in best:
                    continue
                score = similarity(a_title, b_title)
                if score >= floor:
                    best[key] = score

    claimed: set[int] = set()
    top: list[tuple[tuple[int, int], float]] = []
    for pair, score in sorted(best.items(), key=lambda kv: -kv[1]):
        if pair[0] in claimed or pair[1] in claimed:
            continue
        claimed.update(pair)
        top.append((pair, score))

    total = len(top)
    top = top[:limit]
    ids = {pid for pair, _ in top for pid in pair}
    cards = {c["product"].id: c for c in repo.cards_by_ids(session, sorted(ids))}
    items = [
        {"score": round(score, 1), "left": cards[pair[0]], "right": cards[pair[1]]}
        for pair, score in top
        if pair[0] in cards and pair[1] in cards
    ]
    return {"items": items, "total": total}


def rejected_queue(session: Session, limit: int = 50, min_score: float = 0.0) -> dict:
    """Previously rejected pairs, best match first — for second-guessing a no.

    Pairs that have since ended up on one game are dropped: the rejection was
    already overruled, so there is nothing left to reconsider.
    """
    rows = session.exec(select(MergeRejection)).all()
    if not rows:
        return {"items": [], "total": 0}

    ids = {r.product_a_id for r in rows} | {r.product_b_id for r in rows}
    listings = {
        pid: (title, game_id)
        for pid, title, game_id in session.exec(
            select(Product.id, Game.title, Product.game_id)
            .join(Game, Product.game_id == Game.id)
            .where(Product.id.in_(ids))
        )
    }

    scored: list[tuple[tuple[int, int], float]] = []
    for row in rows:
        a, b = row.product_a_id, row.product_b_id
        if a not in listings or b not in listings:
            continue
        if listings[a][1] == listings[b][1]:
            continue
        score = similarity(listings[a][0], listings[b][0])
        if score >= min_score:
            scored.append(((a, b), score))

    scored.sort(key=lambda kv: -kv[1])
    total = len(scored)
    top = scored[:limit]
    card_ids = sorted({pid for pair, _ in top for pid in pair})
    cards = {c["product"].id: c for c in repo.cards_by_ids(session, card_ids)}
    items = [
        {"score": round(score, 1), "left": cards[pair[0]], "right": cards[pair[1]]}
        for pair, score in top
        if pair[0] in cards and pair[1] in cards
    ]
    return {"items": items, "total": total}


def unreject(session: Session, product_id: int, other_id: int) -> None:
    """Forget that two listings were called different games."""
    row = session.get(MergeRejection, _pair(product_id, other_id))
    if row is None:
        return
    session.delete(row)
    session.commit()


def decide_many(session: Session, merges, rejects, unrejects=()) -> dict:
    """Apply a batch of merge/reject decisions, skipping ones that no longer hold.

    A pair can go stale mid-batch — an earlier merge in the same batch may have
    already put both listings on one game — so a failure is counted, not raised.
    """
    applied = {"merged": 0, "rejected": 0, "unrejected": 0, "skipped": 0}
    for a, b in merges:
        try:
            merge(session, a, b)
            applied["merged"] += 1
        except (LookupError, ValueError):
            session.rollback()
            applied["skipped"] += 1
    for a, b in rejects:
        try:
            reject(session, a, b)
            applied["rejected"] += 1
        except (LookupError, ValueError):
            session.rollback()
            applied["skipped"] += 1
    for a, b in unrejects:
        unreject(session, a, b)
        applied["unrejected"] += 1
    return applied


# ---------------------------------------------------------------------------
# Merge / unmerge
# ---------------------------------------------------------------------------


def _absorb_watch(session: Session, target_id: int, source_id: int) -> None:
    """Move a watch from the absorbed game to the surviving one.

    A game can only be watched once, so when both were watched the survivor's
    watch stays and the other is retired — its per-listing alert memory moves
    over, so nothing gets re-announced.
    """
    source_watch = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == source_id, WatchlistItem.active
        )
    ).first()
    if source_watch is None:
        return

    target_watch = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == target_id, WatchlistItem.active
        )
    ).first()

    if target_watch is None:
        source_watch.game_id = target_id
        session.add(source_watch)
        return

    for state in session.exec(
        select(WatchListingState).where(WatchListingState.watch_id == source_watch.id)
    ):
        if session.get(WatchListingState, (target_watch.id, state.product_id)) is None:
            session.add(
                WatchListingState(
                    watch_id=target_watch.id,
                    product_id=state.product_id,
                    last_notified_price=state.last_notified_price,
                )
            )
        session.delete(state)
    if target_watch.target_price is None:
        target_watch.target_price = source_watch.target_price
    source_watch.active = False
    source_watch.game_id = target_id
    session.add(target_watch)
    session.add(source_watch)


def merge(session: Session, product_id: int, other_id: int) -> dict:
    """Put two listings on the same game. The older game survives."""
    a = session.get(Product, product_id)
    b = session.get(Product, other_id)
    if a is None or b is None:
        raise LookupError("Product not found")
    if a.id == b.id:
        raise ValueError("cannot merge a listing with itself")

    stale_rejection = session.get(MergeRejection, _pair(a.id, b.id))
    if stale_rejection:
        # A confirmation outranks an earlier rejection of the same pair.
        session.delete(stale_rejection)

    if a.game_id == b.game_id:
        session.commit()
        return game_payload(session, a.game_id)

    target_id, source_id = sorted([a.game_id, b.game_id])
    target = session.get(Game, target_id)
    source = session.get(Game, source_id)
    if target is None or source is None:
        raise LookupError("Game not found")

    discarded_bgg = None
    if source.bgg_id and source.bgg_id != target.bgg_id:
        if target.bgg_id is None:
            target.bgg_id = source.bgg_id
        else:
            # Two different BGG entries can't both be right; the survivor keeps
            # its link and the other is reported so the user can switch.
            discarded_bgg = source.bgg_id

    # A shorter name is nearly always the cleaner one.
    if len(source.title) < len(target.title):
        target.title = source.title
    target.hidden = target.hidden or source.hidden
    target.note = target.note or source.note
    session.add(target)

    for listing in session.exec(select(Product).where(Product.game_id == source_id)):
        listing.game_id = target_id
        listing.updated_at = datetime.utcnow()
        session.add(listing)

    _absorb_watch(session, target_id, source_id)

    for entry in session.exec(
        select(NotificationLog).where(NotificationLog.game_id == source_id)
    ):
        entry.game_id = target_id
        session.add(entry)

    # The absorbed id keeps pointing at the survivor, so links to it still work.
    session.add(GameAlias(old_game_id=source_id, game_id=target_id))
    for alias in session.exec(select(GameAlias).where(GameAlias.game_id == source_id)):
        alias.game_id = target_id
        session.add(alias)

    session.flush()
    session.delete(source)
    session.commit()
    log.info("merged game %s into %s", source_id, target_id)

    payload = game_payload(session, target_id)
    payload["discarded_bgg_id"] = discarded_bgg
    return payload


def unmerge(session: Session, product_id: int) -> dict:
    """Split one listing off onto a game of its own."""
    listing = session.get(Product, product_id)
    if listing is None:
        raise LookupError("Product not found")

    old_game = session.get(Game, listing.game_id)
    siblings = session.exec(
        select(Product).where(
            Product.game_id == listing.game_id, Product.id != product_id
        )
    ).all()
    if not siblings:
        return game_payload(session, listing.game_id)

    game = Game(
        title=listing.title,
        bgg_id=old_game.bgg_id if old_game else None,
        hidden=old_game.hidden if old_game else False,
    )
    session.add(game)
    session.flush()
    listing.game_id = game.id
    listing.updated_at = datetime.utcnow()
    session.add(listing)
    session.commit()
    log.info("unmerged listing %s to game %s", product_id, game.id)
    return game_payload(session, game.id)


def reject(session: Session, product_id: int, other_id: int) -> None:
    """Record that two listings are not the same game."""
    a = session.get(Product, product_id)
    b = session.get(Product, other_id)
    if a is None or b is None:
        raise LookupError("Product not found")
    if a.id == b.id:
        raise ValueError("cannot reject a listing against itself")
    key = _pair(a.id, b.id)
    if session.get(MergeRejection, key) is None:
        session.add(MergeRejection(product_a_id=key[0], product_b_id=key[1]))
        session.commit()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def resolve_game_id(session: Session, game_id: int) -> int | None:
    """Follow a merged-away id to the game that absorbed it."""
    if session.get(Game, game_id) is not None:
        return game_id
    alias = session.get(GameAlias, game_id)
    return alias.game_id if alias and session.get(Game, alias.game_id) else None


def game_payload(session: Session, game_id: int) -> dict:
    """Everything the game page needs: offers, listing cards, per-shop history."""
    resolved = resolve_game_id(session, game_id)
    game = session.get(Game, resolved) if resolved else None
    if game is None:
        raise LookupError("Game not found")
    game_id = resolved

    compare = repo.compare_summary(session, game_id) or {
        "game_id": game_id,
        "listing_count": 0,
        "store_ids": [],
        "cheapest": None,
        "cheapest_in_stock": None,
        "offers": [],
        "images": [],
    }
    listing_ids = [o["product_id"] for o in compare["offers"]]
    watch = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == game_id, WatchlistItem.active
        )
    ).first()
    return {
        **compare,
        "game": game,
        "watchlist_item": watch,
        "listings": repo.cards_by_ids(session, listing_ids),
        "series": _series(session, listing_ids),
    }


def _series(session: Session, product_ids: list[int], limit: int = 180) -> list[dict]:
    """Per-shop price history, oldest first."""
    if not product_ids:
        return []
    rows = session.exec(
        select(Product, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.product_id == Product.id)
        .where(Product.id.in_(product_ids))
        .order_by(PriceSnapshot.recorded_at.asc())
    ).all()
    by_product: dict[int, dict] = {}
    for product, snap in rows:
        entry = by_product.setdefault(
            product.id,
            {
                "product_id": product.id,
                "store_id": product.store_id,
                "listing_title": product.title,
                "history": [],
            },
        )
        entry["history"].append(
            {
                "price": snap.price,
                "available": snap.available,
                "recorded_at": snap.recorded_at,
            }
        )
    for entry in by_product.values():
        entry["history"] = entry["history"][-limit:]
    return [by_product[pid] for pid in product_ids if pid in by_product]


def apply_bgg_link(session: Session, game_id: int, bgg_id: int | None) -> None:
    """Set (or clear) the game's BGG link."""
    game = session.get(Game, game_id)
    if game is None:
        raise LookupError("Game not found")
    game.bgg_id = bgg_id
    session.add(game)
