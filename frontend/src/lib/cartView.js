/**
 * How the cart page narrows and orders its rows. Pure functions over the
 * payload so the arithmetic stays testable without a DOM.
 */

/** Buy-order is the queue itself; every other sort is a way of looking at it. */
export const SORTS = [
	{ id: 'order', label: 'Buy order' },
	{ id: 'price-asc', label: 'Cheapest first' },
	{ id: 'price-desc', label: 'Dearest first' },
	{ id: 'rating', label: 'Best rated' },
	{ id: 'discount', label: 'Biggest discount' },
	{ id: 'added', label: 'Recently added' }
];

export const PRIORITIES = [
	{ id: 'must', label: 'Must have', tone: 'text-rose-500' },
	{ id: 'normal', label: 'Normal', tone: 'text-muted-foreground' },
	{ id: 'someday', label: 'Someday', tone: 'text-muted-foreground' }
];

/** @param {any} row */
export function rowPrice(row) {
	return row?.offer?.price ?? null;
}

/** What the row costs at the quantity queued. */
export function rowLine(row) {
	const price = rowPrice(row);
	return price == null ? null : price * (row.cart.quantity || 1);
}

/** @param {any} row */
export function rowAvailable(row) {
	return Boolean(row?.offer?.available);
}

/**
 * @param {any[]} rows
 * @param {{ priority?: string|null, storeId?: string|null, inStockOnly?: boolean,
 *           withinBudget?: boolean, cutIndex?: number|null }} opts
 */
export function filterRows(rows, opts = {}) {
	const { priority = null, storeId = null, inStockOnly = false } = opts;
	const cutIndex = opts.withinBudget ? opts.cutIndex : null;
	return rows.filter((row, index) => {
		if (priority && row.cart.priority !== priority) return false;
		if (storeId && row.offer?.store_id !== storeId) return false;
		if (inStockOnly && !rowAvailable(row)) return false;
		// The cutline is a position in the queue, so it only filters the queue's
		// own order — the rows before the first one the budget cannot reach.
		if (cutIndex != null && index >= cutIndex) return false;
		return true;
	});
}

/** @param {any[]} rows @param {string} sort */
export function sortRows(rows, sort) {
	const copy = [...rows];
	const num = (/** @type {number|null} */ v, fallback) => (v == null ? fallback : v);
	switch (sort) {
		case 'price-asc':
			return copy.sort((a, b) => num(rowPrice(a), Infinity) - num(rowPrice(b), Infinity));
		case 'price-desc':
			return copy.sort((a, b) => num(rowPrice(b), -Infinity) - num(rowPrice(a), -Infinity));
		case 'rating':
			return copy.sort(
				(a, b) => num(b.card?.bgg?.bgg_rating, -1) - num(a.card?.bgg?.bgg_rating, -1)
			);
		case 'discount':
			return copy.sort((a, b) => num(b.card?.discount_pct, -1) - num(a.card?.discount_pct, -1));
		case 'added':
			return copy.sort((a, b) => b.cart.id - a.cart.id);
		default:
			return copy;
	}
}

/** Shops appearing in the cart, with how many rows each one holds. */
export function storeOptions(rows) {
	/** @type {Map<string, number>} */
	const counts = new Map();
	for (const row of rows) {
		const id = row.offer?.store_id;
		if (id) counts.set(id, (counts.get(id) ?? 0) + 1);
	}
	return [...counts.entries()].map(([id, count]) => ({ id, count }));
}

/** What each shop's order would cost, as a share of the whole cart. */
export function basketShares(summary) {
	const total = summary?.total || 0;
	return (summary?.by_store ?? []).map((basket) => ({
		...basket,
		share: total > 0 ? basket.total / total : 0
	}));
}
