"""Typo-tolerant title matching shared by the search endpoints.

SQLite has no trigram index and no full-text search on these tables, so
matching happens in Python: titles are normalized, scored against the query,
and ranked. Exact/substring hits always outrank fuzzy hits because the
substring tiers score above 100 and the fuzzy tier is capped at 100.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

_TOKEN_RE = re.compile(r"[0-9a-z]+")

#: Minimum overall score for a non-substring (typo) match to count. Tuned for
#: recall over precision: weak matches are wanted, they just sort to the
#: bottom. Lower = more results, more noise.
FUZZY_CUTOFF = 58

#: Minimum per-word similarity for a query word to count as "recognizable" in
#: a title. Loose enough for a one- or two-character typo ("catn" vs "catan"
#: = 88.9, "carcasone" vs "carcassonne" = 90).
TOKEN_CUTOFF = 72

#: Queries shorter than this only match by substring — two characters of fuzz
#: match nearly every title in the catalog.
MIN_FUZZY_QUERY_LEN = 3


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric runs. Punctuation and spacing are dropped, so
    "Catan: Seafarers (2nd Ed.)" and "catan seafarers 2nd ed" agree."""
    return _TOKEN_RE.findall(text.lower())


def normalize(text: str) -> str:
    return " ".join(tokenize(text))


def score_title(nq: str, nt: str) -> float:
    """Score a normalized query against a normalized title.

    Tiers, highest first: exact, prefix, substring, all-query-words-present,
    fuzzy. Within the substring tiers, a query covering more of the title
    wins, so "catan" ranks the base game above "Catan: Cities & Knights".
    """
    if not nq or not nt:
        return 0.0
    if nt == nq:
        return 200.0
    coverage = 10.0 * len(nq) / len(nt)
    if nt.startswith(nq):
        return 160.0 + coverage
    if nq in nt:
        return 140.0 + coverage

    t_tokens = nt.split()
    if all(any(t.startswith(qt) for t in t_tokens) for qt in nq.split()):
        return 120.0

    if len(nq) < MIN_FUZZY_QUERY_LEN:
        return 0.0
    # Whole-string scorers penalize length mismatch: "catn" against
    # "catan cities knights" scores ~67 because the title is five times longer
    # than the query, so a typo hides every long title. Word-level scoring
    # compares "catn" to "catan" alone and keeps that title in the results.
    return max(
        fuzz.WRatio(nq, nt),
        fuzz.token_set_ratio(nq, nt),
        _word_score(nq.split(), t_tokens),
        _subsequence_score(nq, nt),
    )


def _subsequence_score(nq: str, nt: str) -> float:
    """Score a query whose characters appear in order in the title.

    People type "catbox" for "Cat in the Box" — initials and dropped filler
    words. Every word-level scorer misses that, because "catbox" is not close
    to any single word of the title. Matching characters in order (the trick
    fuzzy file finders use) does catch it.

    Ranked by compactness: characters packed into a short span, landing on
    word starts, score higher than ones scattered across a long title.
    """
    q = nq.replace(" ", "")
    words = nt.split()
    flat = "".join(words)
    if len(q) < MIN_FUZZY_QUERY_LEN or len(q) > len(flat):
        return 0.0

    starts = set()
    pos = 0
    for word in words:
        starts.add(pos)
        pos += len(word)

    matched = []
    i = 0
    for idx, ch in enumerate(flat):
        if ch == q[i]:
            matched.append(idx)
            i += 1
            if i == len(q):
                break
    if i < len(q):
        return 0.0

    span = matched[-1] - matched[0] + 1
    density = len(q) / span
    at_word_start = sum(1 for m in matched if m in starts) / len(q)
    return max(
        55.0 + 30.0 * density + 15.0 * at_word_start,
        _initialism_score(q, words),
    )


def _initialism_score(q: str, words: list[str]) -> float:
    """Score "ttr" against "Ticket to Ride Europe".

    The plain subsequence pass matches greedily and can land mid-word, which
    lets an unrelated long title outscore the title the acronym names. Testing
    the initials on their own fixes the ordering.
    """
    initials = "".join(w[0] for w in words)
    matched = []
    i = 0
    for idx, ch in enumerate(initials):
        if ch == q[i]:
            matched.append(idx)
            i += 1
            if i == len(q):
                break
    if i < len(q):
        return 0.0
    span = matched[-1] - matched[0] + 1
    return 85.0 + 15.0 * len(q) / span


def _word_score(q_tokens: list[str], t_tokens: list[str]) -> float:
    """Mean best-match similarity, but only if every query word is recognizable.

    Requiring the weakest word to clear TOKEN_CUTOFF is what stops "catn" from
    dragging in every title that happens to share a common word.
    """
    best = [max(_token_score(qt, tt) for tt in t_tokens) for qt in q_tokens]
    if min(best) < TOKEN_CUTOFF:
        return 0.0
    return sum(best) / len(best)


def _token_score(qt: str, tt: str) -> float:
    """Similarity of one query word to one title word."""
    if tt.startswith(qt):
        return 100.0
    return fuzz.ratio(qt, tt)


def rank_titles[K](
    query: str,
    candidates: list[tuple[K, str]],
    *,
    limit: int | None = None,
    cutoff: float = FUZZY_CUTOFF,
) -> list[tuple[K, float]]:
    """Rank (key, title) pairs against the query, best first."""
    nq = normalize(query)
    if not nq:
        return []
    scored = []
    for key, title in candidates:
        nt = normalize(title or "")
        score = score_title(nq, nt)
        if score >= cutoff:
            scored.append((key, score, len(nt)))
    # Ties break toward the shorter title: on a typo every "Catan …" edition
    # scores identically, and the base game is the better first result.
    scored.sort(key=lambda row: (-row[1], row[2]))
    ranked = [(key, score) for key, score, _ in scored]
    return ranked[:limit] if limit is not None else ranked
