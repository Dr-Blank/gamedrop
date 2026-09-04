import { describe, it, expect } from 'vitest';
import {
	filterRows,
	sortRows,
	storeOptions,
	basketShares,
	rowLine,
	rowPrice
} from '$lib/cartView.js';

/** @param {number} id */
const row = (id, over = {}) => ({
	cart: { id, game_id: id, quantity: 1, priority: 'normal', ...over.cart },
	offer: { product_id: id, store_id: 's1', price: 100, available: true, ...over.offer },
	card: over.card ?? { bgg: { bgg_rating: 7 }, discount_pct: 10 },
	compare: over.compare ?? null,
	pinned: false,
	price_move: null,
	over_max: false
});

describe('cart rows', () => {
	it('a line is the offer price at the queued quantity', () => {
		expect(rowLine(row(1, { cart: { quantity: 3 } }))).toBe(300);
		expect(rowPrice(row(1, { offer: { price: null } }))).toBe(null);
		expect(rowLine(row(1, { offer: { price: null } }))).toBe(null);
	});

	it('filters by priority, shop and stock', () => {
		const rows = [
			row(1, { cart: { priority: 'must' } }),
			row(2, { offer: { store_id: 's2' } }),
			row(3, { offer: { available: false } })
		];
		expect(filterRows(rows, { priority: 'must' }).map((r) => r.cart.id)).toEqual([1]);
		expect(filterRows(rows, { storeId: 's2' }).map((r) => r.cart.id)).toEqual([2]);
		expect(filterRows(rows, { inStockOnly: true }).map((r) => r.cart.id)).toEqual([1, 2]);
	});

	it('the budget cutline keeps only what the budget reaches', () => {
		const rows = [row(1), row(2), row(3)];
		expect(filterRows(rows, { withinBudget: true, cutIndex: 2 }).map((r) => r.cart.id)).toEqual([
			1, 2
		]);
		// No budget set: the cutline filter is inert rather than emptying the list.
		expect(filterRows(rows, { withinBudget: true, cutIndex: null })).toHaveLength(3);
	});

	it('sorts by price, rating, discount and recency', () => {
		const rows = [
			row(1, { offer: { price: 300 }, card: { bgg: { bgg_rating: 6 }, discount_pct: 5 } }),
			row(2, { offer: { price: 100 }, card: { bgg: { bgg_rating: 9 }, discount_pct: 40 } }),
			row(3, { offer: { price: 200 }, card: { bgg: { bgg_rating: 7 }, discount_pct: 20 } })
		];
		const ids = (sorted) => sorted.map((r) => r.cart.id);
		expect(ids(sortRows(rows, 'price-asc'))).toEqual([2, 3, 1]);
		expect(ids(sortRows(rows, 'price-desc'))).toEqual([1, 3, 2]);
		expect(ids(sortRows(rows, 'rating'))).toEqual([2, 3, 1]);
		expect(ids(sortRows(rows, 'discount'))).toEqual([2, 3, 1]);
		expect(ids(sortRows(rows, 'added'))).toEqual([3, 2, 1]);
	});

	it('buy order leaves the queue as it stands', () => {
		const rows = [row(3), row(1), row(2)];
		expect(sortRows(rows, 'order').map((r) => r.cart.id)).toEqual([3, 1, 2]);
	});

	it('a row with no price sinks instead of leading the cheapest sort', () => {
		const rows = [row(1, { offer: { price: null } }), row(2, { offer: { price: 50 } })];
		expect(sortRows(rows, 'price-asc').map((r) => r.cart.id)).toEqual([2, 1]);
	});

	it('lists the shops in the cart with their row counts', () => {
		const rows = [row(1), row(2), row(3, { offer: { store_id: 's2' } })];
		expect(storeOptions(rows)).toEqual([
			{ id: 's1', count: 2 },
			{ id: 's2', count: 1 }
		]);
	});

	it('baskets carry their share of the cart total', () => {
		const shares = basketShares({
			total: 400,
			by_store: [
				{ store_id: 's1', total: 300, count: 2 },
				{ store_id: 's2', total: 100, count: 1 }
			]
		});
		expect(shares.map((b) => b.share)).toEqual([0.75, 0.25]);
	});

	it('an empty cart has no shares to divide', () => {
		expect(basketShares({ total: 0, by_store: [] })).toEqual([]);
	});
});
