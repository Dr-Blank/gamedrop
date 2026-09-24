/**
 * What a card should show for a game sold by more than one shop.
 *
 * `primary` is the cheapest offer you can actually buy; `blocked` is a cheaper
 * one that is out of stock, and is null when the cheapest offer is buyable —
 * there is nothing to warn about, so nothing is shown.
 *
 * Given a `focusStore`, the card speaks from that shop instead: `primary` is
 * its offer and `rival` is the best price anywhere else, so the card answers
 * "what am I saving by buying here" rather than "who is cheapest".
 *
 * @param {any} compare the card's `compare` payload
 * @param {string|null} focusStore shop to quote from, or null for the cheapest
 */
export function gamePricing(compare, focusStore = null) {
	if (!compare || (compare.listing_count ?? 0) < 2) return null;
	const cheapest = compare.cheapest ?? null;
	const inStock = compare.cheapest_in_stock ?? null;
	if (!cheapest) return null;

	const best = inStock ?? cheapest;
	const focused = focusStore ? cheapestAt(compare, focusStore) : null;
	const primary = focused ?? best;
	// The warning stays inside the frame being quoted: focused on one shop, a
	// cheaper sold-out offer somewhere else is the rival line's business.
	const blocked = cheapestBlocked(compare, primary, focused ? focusStore : null);
	return {
		primary,
		blocked,
		best,
		focused: focused != null,
		// Best price at any other shop — what the quoted one is measured against.
		rival: bestElsewhere(compare, primary),
		allOut: !inStock,
		storeCount: (compare.store_ids ?? []).length,
		listingCount: compare.listing_count ?? 0,
		savings: blocked ? primary.price - blocked.price : 0
	};
}

/** A cheaper offer than the quoted one that cannot be bought, if there is one. */
function cheapestBlocked(compare, primary, storeId) {
	const scope = (compare.offers ?? []).filter(
		(o) => o.price != null && !o.available && (storeId == null || o.store_id === storeId)
	);
	if (!scope.length) return null;
	const cheapest = scope.reduce((a, b) => (b.price < a.price ? b : a));
	return cheapest.price < primary.price ? cheapest : null;
}

/** A shop's own best offer: buyable if it has one, cheapest otherwise. */
function cheapestAt(compare, storeId) {
	const own = (compare.offers ?? []).filter((o) => o.store_id === storeId && o.price != null);
	if (!own.length) return null;
	const byPrice = [...own].sort((a, b) => a.price - b.price);
	return byPrice.find((o) => o.available) ?? byPrice[0];
}

/** The cheapest offer from a shop other than the quoted one. */
function bestElsewhere(compare, quoted) {
	const others = (compare.offers ?? []).filter(
		(o) => o.price != null && o.store_id !== quoted.store_id
	);
	if (!others.length) return null;
	const byPrice = [...others].sort((a, b) => a.price - b.price);
	return byPrice.find((o) => o.available) ?? byPrice[0];
}
