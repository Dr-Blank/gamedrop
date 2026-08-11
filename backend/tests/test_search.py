"""Typo-tolerant, ranked global search."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Game, Store
from app.text_search import FUZZY_CUTOFF, normalize, rank_titles, score_title

from .factories import make_product

TITLES = [
    "Catan",
    "Catan: Cities & Knights",
    "Catan: Seafarers Expansion",
    "Pandemic Legacy Season 1",
    "Ticket to Ride Europe",
    "Azul",
    "Cat in the Box Deluxe Edition",
]


def _seed(session: Session, titles=TITLES, hidden: set[str] | None = None):
    session.add(
        Store(id="s1", name="Store One", type="shopify", base_url="https://s1.com")
    )
    session.commit()
    for i, title in enumerate(titles):
        product = make_product(session, external_id=f"e{i}", title=title)
        if title in (hidden or set()):
            game = session.get(Game, product.game_id)
            game.hidden = True
            session.add(game)
    session.commit()


def _titles(client: TestClient, q: str, **params) -> list[str]:
    res = client.get("/api/search", params={"q": q, **params})
    assert res.status_code == 200
    return [item["product"]["title"] for item in res.json()["items"]]


# --- unit: scoring ---------------------------------------------------------


def test_normalize_strips_punctuation_and_case():
    assert normalize("Catan: Seafarers (2nd Ed.)") == "catan seafarers 2nd ed"


def test_exact_outranks_prefix_outranks_substring():
    exact = score_title("catan", "catan")
    prefix = score_title("catan", "catan seafarers expansion")
    substring = score_title("catan", "the settlers of catan")
    assert exact > prefix > substring


def test_substring_tiers_outrank_any_fuzzy_match():
    substring = score_title("catan", "the settlers of catan")
    fuzzy = score_title("catan", "catn")
    assert substring > 100 >= fuzzy


def test_shorter_title_wins_on_equal_tier():
    assert score_title("catan", "catan") > score_title("catan", "catan seafarers")


def test_short_queries_do_not_fuzzy_match():
    # "az" is under MIN_FUZZY_QUERY_LEN, so it may only match by substring.
    assert score_title("az", "azul") > 0
    assert score_title("az", "catan") == 0


def test_typo_matches_long_titles_not_only_short_ones():
    # Whole-string scorers penalize the length gap and drop long titles, so a
    # typo used to return far fewer results than the correct spelling.
    assert score_title("catn", "catan cities knights") >= 72
    assert score_title("catn", "the settlers of catan 5 6 player extension") >= 72


def test_dropped_filler_words_match():
    # "catbox" is what people type for "Cat in the Box" — no single word of the
    # title is close to it, so only in-order character matching finds it.
    box = score_title("catbox", "cat in the box deluxe edition")
    assert box >= FUZZY_CUTOFF
    assert box > score_title("catbox", "flamecraft board game")


def test_initials_match_and_rank_first():
    ttr = score_title("ttr", "ticket to ride europe")
    assert ttr >= FUZZY_CUTOFF
    assert ttr > score_title("ttr", "catan trade build settle board game")


def test_weak_matches_rank_below_real_ones():
    # Scoring favours recall, so unrelated titles may still appear — they just
    # have to sort below the titles the query actually names.
    assert score_title("catn", "ticket to ride europe") < score_title("catn", "catan")


def test_garbage_query_still_matches_nothing():
    assert score_title("xyzzy", "catan") < FUZZY_CUTOFF


def test_rank_titles_limit_and_order():
    ranked = rank_titles("catan", list(enumerate(TITLES)), limit=2)
    assert [TITLES[i] for i, _ in ranked] == ["Catan", "Catan: Cities & Knights"]


# --- API: typo tolerance ---------------------------------------------------


def test_search_finds_result_despite_typo(client: TestClient, session: Session):
    _seed(session)
    assert "Catan" in _titles(client, "catn")


def test_typo_recall_matches_correct_spelling(client: TestClient, session: Session):
    _seed(session)
    assert set(_titles(client, "catn")) == set(_titles(client, "catan"))


def test_typo_ranks_base_game_first(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "catn")[0] == "Catan"


def test_search_finds_result_despite_transposition(
    client: TestClient, session: Session
):
    _seed(session)
    assert "Pandemic Legacy Season 1" in _titles(client, "pandmeic")


def test_search_matches_reordered_words(client: TestClient, session: Session):
    _seed(session)
    assert "Catan: Seafarers Expansion" in _titles(client, "seafarers catan")


def test_search_ignores_punctuation(client: TestClient, session: Session):
    _seed(session)
    assert "Catan: Cities & Knights" in _titles(client, "catan cities and knights")


def test_search_ranks_squashed_query_first(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "catbox")[0] == "Cat in the Box Deluxe Edition"


def test_search_ranks_initials_first(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "ttr")[0] == "Ticket to Ride Europe"


# --- API: ranking and existing guarantees ----------------------------------


def test_exact_match_ranks_first(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "catan")[0] == "Catan"


def test_search_matches_title_substring(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "cat")[0].startswith("Catan")


def test_search_blank_returns_empty(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "") == []


def test_search_nonsense_returns_empty(client: TestClient, session: Session):
    _seed(session)
    assert _titles(client, "zzzzqqqqwwww") == []


def test_search_excludes_hidden_products(client: TestClient, session: Session):
    _seed(session, hidden={"Catan"})
    assert "Catan" not in _titles(client, "catan")


def test_search_respects_limit(client: TestClient, session: Session):
    _seed(session)
    assert len(_titles(client, "catan", limit=2)) == 2


def test_prices_search_by_name_is_typo_tolerant(client: TestClient, session: Session):
    _seed(session)
    res = client.get("/api/prices/search", params={"q": "catn"})
    assert res.status_code == 200
    assert "Catan" in [r["product"]["title"] for r in res.json()]
