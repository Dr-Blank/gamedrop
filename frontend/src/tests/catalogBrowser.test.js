import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { afterNavigate, goto } from '$app/navigation';

// Chart.js needs a real canvas, which jsdom has not got.
vi.mock('$lib/components/PriceChart.svelte', async () => ({
	default: (await import('./fixtures/Blank.svelte')).default
}));

vi.mock('$lib/api.js', () => ({
	browseFields: vi.fn(),
	browseStores: vi.fn(),
	browseQuery: vi.fn(),
	createShelf: vi.fn(),
	patchGame: vi.fn(),
	setOverride: vi.fn(),
	clearOverride: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import Browse from '../routes/browse/+page.svelte';
import * as api from '$lib/api.js';

describe('browse page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
		api.browseQuery.mockResolvedValue({ items: [], total: 0 });
	});

	async function renderPage() {
		render(Browse);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'load' });
	}

	it('queries without a preset, with hidden games trailing the rest', async () => {
		await renderPage();
		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: null,
			hidden_last: true
		});
	});

	it('marks off the hidden tail once the visible results run out', async () => {
		const card = (id, title, hidden) => ({
			product: { id, game_id: id, title, store_id: 'satyam', url: 'https://x/p' },
			game: { id, title, hidden, bgg_id: null, note: null },
			latest_price: { price: 610, available: true },
			bgg: null,
			override: null,
			watchlist: null
		});
		api.browseQuery.mockResolvedValue({
			items: [card(1, 'Azul', false), card(2, 'Catan', true), card(3, 'Dune', true)],
			total: 3
		});
		await renderPage();

		await screen.findByText('Azul');
		// One divider, ahead of the first hidden card — not one per hidden card.
		expect(screen.getAllByText('Hidden games')).toHaveLength(1);
	});

	it('adds and drops its quick filter on repeated clicks', async () => {
		await renderPage();
		const button = screen.getByRole('button', { name: /Not merged/ });

		await fireEvent.click(button);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'link' });
		expect(api.browseQuery.mock.calls.at(-1)[0].filters.conditions).toEqual([
			{ type: 'condition', field: 'store_count', op: 'eq', value: 1 }
		]);

		await fireEvent.click(button);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'link' });
		expect(api.browseQuery.mock.calls.at(-1)[0].filters).toBeNull();
	});

	it('keeps the controls a plain catalog view owns', async () => {
		await renderPage();
		expect(screen.getByRole('heading', { name: 'Browse' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Not merged/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Sort/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Filters/ })).toBeInTheDocument();
	});
});

describe('browse perspective and card expansion', () => {
	const stores = [
		{ id: 'shop-a', name: 'Shop A' },
		{ id: 'shop-b', name: 'Shop B' }
	];

	const offer = (storeId, productId, price, available = true) => ({
		product_id: productId,
		store_id: storeId,
		price,
		available,
		compare_at_price: null,
		url: `https://${storeId}/p`,
		price_history: [{ price, available, recorded_at: '2026-01-01T00:00:00' }]
	});

	const twoShopCard = () => ({
		product: { id: 1, game_id: 9, title: 'Azul', store_id: 'shop-a', url: 'https://shop-a/p' },
		game: { id: 9, title: 'Azul', hidden: false, bgg_id: null, note: null },
		latest_price: { price: 400, available: true },
		bgg: null,
		override: null,
		watchlist: null,
		compare: {
			game_id: 9,
			listing_count: 2,
			store_ids: ['shop-a', 'shop-b'],
			cheapest: offer('shop-a', 1, 400),
			cheapest_in_stock: offer('shop-a', 1, 400),
			offers: [offer('shop-a', 1, 400), offer('shop-b', 2, 600)],
			images: []
		}
	});

	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue(stores);
		api.browseQuery.mockResolvedValue({ items: [twoShopCard()], total: 1 });
	});

	async function renderPage() {
		render(Browse);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'load' });
		await screen.findByText('Azul');
	}

	it('quotes the cheapest shop until one is picked', async () => {
		await renderPage();
		expect(screen.getByText(/at shop-a/)).toBeInTheDocument();
	});

	it('quotes the picked shop and keeps it in the URL', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Shop B/ }));
		expect(screen.getByText(/at shop-b/)).toBeInTheDocument();
		expect(screen.getByText(/200 more than shop-a/)).toBeInTheDocument();
		expect(goto.mock.calls.at(-1)[0]).toContain('v=shop-b');
	});

	it('does not refetch for a change that only rewords the cards', async () => {
		await renderPage();
		const before = api.browseQuery.mock.calls.length;
		await fireEvent.click(screen.getByRole('button', { name: /Shop B/ }));
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'goto' });
		expect(api.browseQuery.mock.calls).toHaveLength(before);
	});

	it('marks the cheapest-shop view with an empty perspective, not a name', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Cheapest shop/ }));
		expect(goto.mock.calls.at(-1)[0]).toContain('v=');
		expect(goto.mock.calls.at(-1)[0]).not.toContain('v=best');
	});

	it('opens every shop on the card without leaving the grid', async () => {
		await renderPage();
		expect(screen.queryByRole('table')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Compare every shop/ }));
		expect(screen.getByRole('table')).toBeInTheDocument();
		// The panel's slide-out never settles under jsdom, so the toggle state is
		// what says it closed.
		await fireEvent.click(screen.getByRole('button', { name: /Collapse/ }));
		expect(screen.getByRole('button', { name: /Compare every shop/ })).toHaveAttribute(
			'aria-expanded',
			'false'
		);
	});
});
