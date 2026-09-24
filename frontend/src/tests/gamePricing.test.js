import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

// Chart.js needs a real canvas, which jsdom has not got.
vi.mock('$lib/components/PriceChart.svelte', async () => ({
	default: (await import('./fixtures/Blank.svelte')).default
}));

import ProductCard from '$lib/components/ProductCard.svelte';
import { gamePricing } from '$lib/gamePricing.js';
import { alignSeries, segmentInStock } from '$lib/priceSeries.js';

const offer = (over = {}) => ({
	product_id: 1,
	store_id: 'store-a',
	price: 400,
	available: true,
	compare_at_price: null,
	url: 'https://a/p',
	price_history: [{ price: 400, available: true, recorded_at: '2026-01-01T00:00:00' }],
	...over
});

function compare(offers, over = {}) {
	const priced = [...offers].sort((a, b) => a.price - b.price);
	const inStock = priced.filter((o) => o.available);
	return {
		game_id: 7,
		listing_count: offers.length,
		store_ids: [...new Set(offers.map((o) => o.store_id))],
		cheapest: priced[0] ?? null,
		cheapest_in_stock: inStock[0] ?? null,
		offers: priced,
		images: [],
		...over
	};
}

describe('gamePricing', () => {
	it('is null when only one shop sells the game', () => {
		expect(gamePricing(null)).toBeNull();
		expect(gamePricing(compare([offer()]))).toBeNull();
	});

	it('quotes the cheapest offer and hides alternatives when it is in stock', () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, price: 400, available: true }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
			])
		);
		expect(pricing.primary.price).toBe(400);
		expect(pricing.blocked).toBeNull();
		expect(pricing.allOut).toBe(false);
	});

	it('quotes the buyable price and flags the cheaper out-of-stock one', () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, price: 400, available: false }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
			])
		);
		expect(pricing.primary.price).toBe(600);
		expect(pricing.primary.store_id).toBe('store-b');
		expect(pricing.blocked.price).toBe(400);
		expect(pricing.savings).toBe(200);
	});

	it('falls back to the cheapest when nothing is in stock', () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, price: 400, available: false }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: false })
			])
		);
		expect(pricing.primary.price).toBe(400);
		expect(pricing.allOut).toBe(true);
		expect(pricing.blocked).toBeNull();
	});
});

describe("gamePricing from one shop's side", () => {
	const threeShops = () =>
		compare([
			offer({ product_id: 1, store_id: 'a', price: 400, available: true }),
			offer({ product_id: 2, store_id: 'b', price: 500, available: true }),
			offer({ product_id: 3, store_id: 'c', price: 900, available: true })
		]);

	it('quotes the focused shop even when another is cheaper', () => {
		const pricing = gamePricing(threeShops(), 'b');
		expect(pricing.primary.store_id).toBe('b');
		expect(pricing.focused).toBe(true);
		expect(pricing.best.store_id).toBe('a');
	});

	it('measures the quote against the best price at any other shop', () => {
		expect(gamePricing(threeShops(), 'b').rival.store_id).toBe('a');
		expect(gamePricing(threeShops(), 'a').rival.store_id).toBe('b');
	});

	it("warns only about the focused shop's own sold-out offer", () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, store_id: 'a', price: 300, available: false }),
				offer({ product_id: 2, store_id: 'b', price: 500, available: true })
			]),
			'b'
		);
		// The cheaper sold-out offer is at another shop — the rival line's job.
		expect(pricing.blocked).toBeNull();
		expect(pricing.savings).toBe(0);
		expect(pricing.rival.store_id).toBe('a');
	});

	it('still flags a sold-out bargain at the focused shop itself', () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, store_id: 'b', price: 300, available: false }),
				offer({ product_id: 2, store_id: 'b', price: 500, available: true }),
				offer({ product_id: 3, store_id: 'a', price: 900, available: true })
			]),
			'b'
		);
		expect(pricing.primary.price).toBe(500);
		expect(pricing.blocked.price).toBe(300);
		expect(pricing.savings).toBe(200);
	});

	it('falls back to the cheapest when the focused shop does not sell it', () => {
		const pricing = gamePricing(threeShops(), 'not-a-shop');
		expect(pricing.primary.store_id).toBe('a');
		expect(pricing.focused).toBe(false);
	});

	it("prefers a shop's buyable listing over its cheaper sold-out one", () => {
		const pricing = gamePricing(
			compare([
				offer({ product_id: 1, store_id: 'a', price: 300, available: false }),
				offer({ product_id: 2, store_id: 'a', price: 450, available: true }),
				offer({ product_id: 3, store_id: 'b', price: 500, available: true })
			]),
			'a'
		);
		expect(pricing.primary.price).toBe(450);
	});
});

describe('ProductCard for a game sold by two shops', () => {
	const item = {
		product: {
			id: 1,
			game_id: 7,
			title: 'Catan',
			store_id: 'store-a',
			url: 'https://a/p',
			image_url: null
		},
		game: { id: 7, title: 'Catan', hidden: false, bgg_id: null, note: null },
		latest_price: { price: 400, available: false, compare_at_price: null },
		bgg: null,
		override: null,
		discount_pct: null,
		compare: compare([
			offer({ product_id: 1, price: 400, available: false }),
			offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
		])
	};

	it('shows the buyable price, its store, and the blocked cheaper offer', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByText(/600/)).toBeInTheDocument();
		expect(screen.getByText(/at store-b/)).toBeInTheDocument();
		expect(screen.getByText(/out of stock/i)).toBeInTheDocument();
		expect(screen.getByText('2 stores')).toBeInTheDocument();
	});

	it('shows in stock, because the quoted offer is the buyable one', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByText('In stock')).toBeInTheDocument();
	});

	it('quotes the shop in focus and says what it costs over the cheapest', () => {
		const focusItem = {
			...item,
			compare: compare([
				offer({ product_id: 1, store_id: 'store-a', price: 400, available: true }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
			])
		};
		render(ProductCard, { props: { item: focusItem, focusStore: 'store-b' } });
		expect(screen.getByText(/at store-b/)).toBeInTheDocument();
		expect(screen.getByText(/200 more than store-a/)).toBeInTheDocument();
	});

	it('opens the shop comparison only once expanded', async () => {
		const onexpand = vi.fn();
		const { rerender } = render(ProductCard, { props: { item, onexpand } });
		expect(screen.queryByRole('table')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Compare every shop/ }));
		expect(onexpand).toHaveBeenCalledWith(7);

		await rerender({ item, onexpand, expanded: true });
		expect(screen.getByRole('table')).toBeInTheDocument();
	});

	it('drops the comparison line when the cheapest offer is buyable', () => {
		const clean = {
			...item,
			compare: compare([
				offer({ product_id: 1, price: 400, available: true }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
			])
		};
		render(ProductCard, { props: { item: clean } });
		expect(screen.queryByText(/out of stock/i)).not.toBeInTheDocument();
		expect(screen.getByText(/400/)).toBeInTheDocument();
	});
});

describe('alignSeries', () => {
	it('shares one day axis and forward-fills each store', () => {
		const { labels, datasets } = alignSeries([
			{
				store_id: 'a',
				history: [
					{ price: 100, recorded_at: '2026-01-01T00:00:00' },
					{ price: 90, recorded_at: '2026-01-03T00:00:00' }
				]
			},
			{ store_id: 'b', history: [{ price: 120, recorded_at: '2026-01-02T00:00:00' }] }
		]);
		expect(labels).toEqual(['2026-01-01', '2026-01-02', '2026-01-03']);
		expect(datasets[0].data).toEqual([100, 100, 90]);
		// Null before a store's first snapshot, then carried forward.
		expect(datasets[1].data).toEqual([null, 120, 120]);
		expect(datasets[1].label).toBe('b');
	});

	it('marks scraped days and carries the last known stock state', () => {
		const { datasets } = alignSeries([
			{
				store_id: 'a',
				history: [
					{ price: 100, available: true, recorded_at: '2026-01-01T00:00:00' },
					{ price: 100, available: false, recorded_at: '2026-01-03T00:00:00' }
				]
			},
			{
				store_id: 'b',
				history: [{ price: 120, available: true, recorded_at: '2026-01-02T00:00:00' }]
			}
		]);
		expect(datasets[0].real).toEqual([true, false, true]);
		expect(datasets[0].available).toEqual([true, true, false]);
		// A store scraped on one day only owns that one point.
		expect(datasets[1].real).toEqual([false, true, false]);
		expect(datasets[1].available).toEqual([null, true, true]);
	});

	it('dashes only the stretch after a shop went out of stock', () => {
		const { datasets } = alignSeries([
			{
				store_id: 'a',
				history: [
					{ price: 2899, available: true, recorded_at: '2026-06-12T00:00:00' },
					{ price: 2899, available: false, recorded_at: '2026-06-14T00:00:00' },
					{ price: 2199, available: true, recorded_at: '2026-07-22T00:00:00' }
				]
			}
		]);
		const { available } = datasets[0];
		expect(segmentInStock(available, 0)).toBe(true);
		expect(segmentInStock(available, 1)).toBe(false);
		expect(segmentInStock(available, 2)).toBe(true);
	});

	it('returns empty axes for no data', () => {
		expect(alignSeries([]).labels).toEqual([]);
	});
});
