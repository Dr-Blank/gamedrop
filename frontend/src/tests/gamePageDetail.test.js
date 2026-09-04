import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';

vi.mock('$lib/api.js', () => ({
	getGame: vi.fn(),
	patchGame: vi.fn(),
	listingDetail: vi.fn(),
	bggGame: vi.fn().mockResolvedValue(null),
	linkBgg: vi.fn(),
	unlinkBgg: vi.fn(),
	bggRefresh: vi.fn(),
	setOverride: vi.fn(),
	clearOverride: vi.fn(),
	hideProduct: vi.fn(),
	unhideProduct: vi.fn(),
	unmergeProduct: vi.fn(),
	patchWatchlistItem: vi.fn(),
	ignoreSnapshot: vi.fn(),
	restoreSnapshot: vi.fn(),
	addSnapshot: vi.fn(),
	deleteSnapshot: vi.fn(),
	getWatchlist: vi.fn().mockResolvedValue([]),
	addWatchlist: vi.fn(),
	removeWatchlist: vi.fn(),
	getStores: vi.fn().mockResolvedValue([]),
	mergeSuggestions: vi.fn().mockResolvedValue([]),
	mergeProducts: vi.fn(),
	getCart: vi.fn().mockResolvedValue({ items: [] }),
	addToCart: vi.fn(),
	removeFromCart: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));
vi.mock('$app/stores', () => ({
	page: readable({ url: new URL('http://localhost/games/1'), params: { id: '1' } }),
	navigating: readable(null),
	updated: readable(false)
}));
// jsdom has no canvas context; the chart is not what these tests are about.
vi.mock('chart.js', () => {
	class Chart {
		static register() {}
		destroy() {}
	}
	return {
		Chart,
		LineController: {},
		LineElement: {},
		PointElement: {},
		LinearScale: {},
		CategoryScale: {},
		Filler: {},
		Tooltip: {}
	};
});

import GamePage from '../routes/games/[id]/+page.svelte';
import * as api from '$lib/api.js';

const snap = (price, at) => ({ id: price, price, available: true, recorded_at: at });

const offer = {
	product_id: 5,
	store_id: 'shop-a',
	price: 2499,
	available: true,
	url: 'https://example-shop.test/p/5'
};

function payload(overrides = {}) {
	return {
		game: { id: 1, title: 'Some Game', bgg_id: null },
		offers: [offer],
		store_ids: ['shop-a'],
		cheapest_in_stock: offer,
		series: [{ store_id: 'shop-a', product_id: 5, history: [] }],
		watchlist_item: null,
		...overrides
	};
}

async function renderGame(over = {}) {
	api.getGame.mockResolvedValue(payload(over));
	api.listingDetail.mockResolvedValue({
		override: null,
		history: [
			snap(1999, '2026-08-01T00:00:00'),
			snap(3499, '2026-08-05T00:00:00'),
			snap(2499, '2026-08-09T00:00:00')
		]
	});
	const r = render(GamePage);
	await waitFor(() => expect(screen.getByText('Some Game')).toBeInTheDocument());
	return r;
}

describe('game page price extremes', () => {
	it('says how far the price stands from each extreme, in rupees', async () => {
		await renderGame();
		await waitFor(() => expect(screen.getByText('ATL ₹2,000')).toBeInTheDocument());
		expect(screen.getByText('· ATH ₹3,500')).toBeInTheDocument();
		expect(screen.getByText('+₹500')).toBeInTheDocument();
		expect(screen.getByText('−₹1,000')).toBeInTheDocument();
	});
});

describe('game page store link', () => {
	it('wears the store accent', async () => {
		await renderGame();
		const link = await screen.findByRole('link', { name: /View at shop-a/ });
		expect(link.getAttribute('style')).toMatch(/border-color: rgba\(/);
		expect(link).toHaveAttribute('href', offer.url);
	});
});

describe('game page BGG linking', () => {
	beforeEach(() => {
		vi.stubGlobal('open', vi.fn());
	});

	it('opens the search and focuses the paste field in one click', async () => {
		await renderGame();
		const button = screen.getByRole('button', { name: /Link BGG/ });
		button.dispatchEvent(new MouseEvent('click', { bubbles: true }));

		const field = await screen.findByPlaceholderText('Paste BGG URL…');
		expect(window.open).toHaveBeenCalledOnce();
		expect(window.open.mock.calls[0][0]).toMatch(/Some\+Game|Some%20Game/);
		expect(document.activeElement).toBe(field);
	});
});
