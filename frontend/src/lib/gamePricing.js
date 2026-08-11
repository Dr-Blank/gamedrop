/**
 * What a card should show for a game sold by more than one shop.
 *
 * `primary` is the cheapest offer you can actually buy; `blocked` is a cheaper
 * one that is out of stock, and is null when the cheapest offer is buyable —
 * there is nothing to warn about, so nothing is shown.
 *
 * @param {any} compare the card's `compare` payload
 */
export function gamePricing(compare) {
	if (!compare || (compare.listing_count ?? 0) < 2) return null;
	const cheapest = compare.cheapest ?? null;
	const inStock = compare.cheapest_in_stock ?? null;
	if (!cheapest) return null;

	const primary = inStock ?? cheapest;
	const blocked = inStock && cheapest.product_id !== inStock.product_id ? cheapest : null;
	return {
		primary,
		blocked,
		allOut: !inStock,
		storeCount: (compare.store_ids ?? []).length,
		listingCount: compare.listing_count ?? 0,
		savings: blocked ? primary.price - blocked.price : 0
	};
}

/** @param {number|null|undefined} n */
export function inr(n) {
	if (n == null) return '—';
	return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
