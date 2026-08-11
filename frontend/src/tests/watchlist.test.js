import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';

// Mock the API + toast so the page renders in isolation.
vi.mock('$lib/api.js', () => ({
	getWatchlist: vi.fn(),
	removeWatchlist: vi.fn(),
	updateWatchlist: vi.fn(),
	addWatchlist: vi.fn(),
	priceSearch: vi.fn(),
	priceHistory: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import Watchlist from '../routes/watchlist/+page.svelte';
import * as api from '$lib/api.js';

const card = {
	product: {
		id: 2,
		game_id: 5,
		title: 'Catan',
		store_id: 'satyam',
		url: 'https://x/p',
		image_url: null
	},
	game: { id: 5, title: 'Catan', hidden: false, bgg_id: null, note: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5,
	watchlist: { id: 1, target_price: null, product_id: 2 }
};

describe('watchlist page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.priceHistory.mockResolvedValue({ history: [] });
	});

	// Regression: the page imported onMount but never called it, so load() never
	// ran — watchlist stayed empty and nothing rendered even with items present.
	it('fetches the watchlist on mount and renders the items', async () => {
		api.getWatchlist.mockResolvedValue([card]);
		render(Watchlist);

		await waitFor(() => expect(api.getWatchlist).toHaveBeenCalledOnce());
		expect(await screen.findByText('Catan')).toBeInTheDocument();
		expect(screen.getByText(/1 game tracked/)).toBeInTheDocument();
	});

	it('shows the empty state when the watchlist is empty', async () => {
		api.getWatchlist.mockResolvedValue([]);
		render(Watchlist);

		expect(await screen.findByText(/Your watchlist is empty/)).toBeInTheDocument();
	});
});
