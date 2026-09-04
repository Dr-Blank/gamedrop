import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api.js', () => ({
	getCart: vi.fn(),
	addToCart: vi.fn(),
	removeFromCart: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import { cart } from '$lib/cart.svelte.js';
import * as api from '$lib/api.js';

const item = { game: { id: 7, title: 'Catan' }, product: { id: 70, game_id: 7 } };

describe('cart store', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		cart.map = new Map();
	});

	it('load() builds a game_id -> cart_id map', async () => {
		api.getCart.mockResolvedValue({
			items: [{ cart: { id: 5, game_id: 7 } }, { cart: { id: 6, game_id: 8 } }]
		});
		await cart.load();
		expect(cart.has(7)).toBe(true);
		expect(cart.count).toBe(2);
	});

	it('toggle() queues the listing without pinning its shop', async () => {
		api.addToCart.mockResolvedValue({ id: 5 });
		await cart.toggle(item);
		expect(api.addToCart).toHaveBeenCalledWith({ product_id: 70 });
		expect(cart.has(7)).toBe(true);
	});

	it('toggle() removes when already queued', async () => {
		cart.map = new Map([[7, 5]]);
		api.removeFromCart.mockResolvedValue({ ok: true });
		await cart.toggle(item);
		expect(api.removeFromCart).toHaveBeenCalledWith(5);
		expect(cart.has(7)).toBe(false);
	});

	it('load() failure leaves the store usable (un-queued)', async () => {
		api.getCart.mockRejectedValue(new Error('offline'));
		await cart.load();
		expect(cart.has(7)).toBe(false);
		expect(cart.ready).toBe(true);
	});

	it('sync() re-keys the map from a cart page payload', () => {
		cart.sync([{ cart: { id: 9, game_id: 3 } }]);
		expect(cart.has(3)).toBe(true);
		expect(cart.count).toBe(1);
	});
});
