import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ProductCard from '$lib/components/ProductCard.svelte';
import { gamePricing, inr } from '$lib/gamePricing.js';
import { alignSeries } from '$lib/priceSeries.js';

const offer = (over = {}) => ({
	product_id: 1,
	store_id: 'store-a',
	price: 400,
	available: true,
	compare_at_price: null,
	url: 'https://a/p',
	price_history: [{ price: 400 }],
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
		render(ProductCard, { props: { item, variant: 'browse' } });
		expect(screen.getByText(/600/)).toBeInTheDocument();
		expect(screen.getByText(/at store-b/)).toBeInTheDocument();
		expect(screen.getByText(/out of stock/i)).toBeInTheDocument();
		expect(screen.getByText('2 stores')).toBeInTheDocument();
	});

	it('shows in stock, because the quoted offer is the buyable one', () => {
		render(ProductCard, { props: { item, variant: 'browse' } });
		expect(screen.getByText('In stock')).toBeInTheDocument();
	});

	it('drops the comparison line when the cheapest offer is buyable', () => {
		const clean = {
			...item,
			compare: compare([
				offer({ product_id: 1, price: 400, available: true }),
				offer({ product_id: 2, store_id: 'store-b', price: 600, available: true })
			])
		};
		render(ProductCard, { props: { item: clean, variant: 'browse' } });
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

	it('returns empty axes for no data', () => {
		expect(alignSeries([]).labels).toEqual([]);
	});
});

describe('inr', () => {
	it('formats and handles missing prices', () => {
		expect(inr(1234)).toBe('₹1,234');
		expect(inr(null)).toBe('—');
	});
});
