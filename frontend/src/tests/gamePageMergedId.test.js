import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';

vi.mock('$lib/cart.svelte.js', () => ({
	cart: { has: () => false, item: () => null, toggle: vi.fn(), patch: vi.fn() }
}));
vi.mock('$lib/watchlist.svelte.js', () => ({
	watchlist: { has: () => false, toggle: vi.fn() }
}));
vi.mock('$lib/api.js', () => ({
	getGame: vi.fn(),
	listingDetail: vi.fn().mockResolvedValue({ override: null, history: [] }),
	bggGame: vi.fn().mockResolvedValue(null),
	patchWatchlistItem: vi.fn(),
	getStores: vi.fn().mockResolvedValue([]),
	mergeSuggestions: vi.fn().mockResolvedValue([])
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));
vi.mock('$app/stores', () => ({
	page: readable({
		url: new URL('http://localhost/games/7?store=shop-a'),
		params: { id: '7' }
	}),
	navigating: readable(null),
	updated: readable(false)
}));
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
import { goto } from '$app/navigation';

const offer = { product_id: 5, store_id: 'shop-a', price: 999, available: true, url: '' };

function payload(id) {
	return {
		game: { id, title: 'Some Game', bgg_id: null },
		offers: [offer],
		store_ids: ['shop-a'],
		cheapest_in_stock: offer,
		series: [],
		watchlist_item: null
	};
}

describe('game page on a merged-away id', () => {
	beforeEach(() => vi.clearAllMocks());

	it('moves to the surviving game, keeping the shop', async () => {
		api.getGame.mockResolvedValue(payload(3));
		render(GamePage);
		await waitFor(() =>
			expect(goto).toHaveBeenCalledWith('/games/3?store=shop-a', { replaceState: true })
		);
	});

	it('stays put when the id is already canonical', async () => {
		api.getGame.mockResolvedValue(payload(7));
		render(GamePage);
		await waitFor(() => expect(api.listingDetail).toHaveBeenCalled());
		expect(goto).not.toHaveBeenCalled();
	});
});
