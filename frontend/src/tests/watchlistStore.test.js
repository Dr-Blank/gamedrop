import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api.js', () => ({
	getWatchlist: vi.fn(),
	addWatchlist: vi.fn(),
	removeWatchlist: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import { watchlist } from '$lib/watchlist.svelte.js';
import * as api from '$lib/api.js';

const item = { product: { id: 7, title: 'Catan' } };

describe('watchlist store', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		watchlist.map = new Map();
	});

	it('load() builds a product_id -> watchlist_id map', async () => {
		api.getWatchlist.mockResolvedValue([
			{ product: { id: 7 }, watchlist: { id: 99 } },
			{ product: { id: 8 }, watchlist: { id: 100 } }
		]);
		await watchlist.load();
		expect(watchlist.has(7)).toBe(true);
		expect(watchlist.has(8)).toBe(true);
		expect(watchlist.has(9)).toBe(false);
	});

	it('toggle() adds when not watched', async () => {
		api.addWatchlist.mockResolvedValue({ id: 99 });
		await watchlist.toggle(item);
		expect(api.addWatchlist).toHaveBeenCalledWith(7, null);
		expect(watchlist.has(7)).toBe(true);
	});

	it('toggle() removes when already watched', async () => {
		watchlist.map = new Map([[7, 99]]);
		api.removeWatchlist.mockResolvedValue({ ok: true });
		await watchlist.toggle(item);
		expect(api.removeWatchlist).toHaveBeenCalledWith(99);
		expect(watchlist.has(7)).toBe(false);
	});

	it('load() failure leaves the store usable (un-watched)', async () => {
		api.getWatchlist.mockRejectedValue(new Error('offline'));
		await watchlist.load();
		expect(watchlist.has(7)).toBe(false);
		expect(watchlist.ready).toBe(true);
	});
});
