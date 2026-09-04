import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/svelte';
import { readable } from 'svelte/store';

const { toggle, patch, queued, row } = vi.hoisted(() => ({
	toggle: vi.fn(),
	patch: vi.fn(),
	queued: { value: false },
	row: { value: /** @type {any} */ (null) }
}));
vi.mock('$lib/cart.svelte.js', () => ({
	cart: { has: () => queued.value, item: () => row.value, toggle, patch }
}));

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
	mergeProducts: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));
vi.mock('$app/stores', () => ({
	page: readable({ url: new URL('http://localhost/games/1'), params: { id: '1' } }),
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

const offerA = {
	product_id: 5,
	store_id: 'shop-a',
	price: 2499,
	available: true,
	url: 'https://example-shop.test/p/5'
};
const offerB = {
	product_id: 6,
	store_id: 'shop-b',
	price: 1999,
	available: true,
	url: 'https://other-shop.test/p/6'
};

async function renderGame(over = {}) {
	api.getGame.mockResolvedValue({
		game: { id: 1, title: 'Some Game', bgg_id: null },
		offers: [offerA],
		store_ids: ['shop-a'],
		cheapest_in_stock: offerA,
		series: [{ store_id: 'shop-a', product_id: 5, history: [] }],
		watchlist_item: null,
		...over
	});
	api.listingDetail.mockResolvedValue({ override: null, history: [] });
	const r = render(GamePage);
	await waitFor(() => expect(screen.getByText('Some Game')).toBeInTheDocument());
	return r;
}

describe('game page cart button', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		queued.value = false;
		row.value = null;
	});

	it('queues the game from the listing on show', async () => {
		await renderGame();
		await fireEvent.click(screen.getByLabelText('Add to cart'));
		expect(toggle).toHaveBeenCalledWith({
			game: { id: 1, title: 'Some Game', bgg_id: null },
			product: { id: 5, game_id: 1 }
		});
	});

	it('sits next to the watch button', async () => {
		const { container } = await renderGame();
		const row = screen.getByLabelText('Add to cart').closest('div');
		expect(row?.textContent).toContain('Watch');
		expect(container).toBeTruthy();
	});

	it('reads as queued once the game is in the cart', async () => {
		queued.value = true;
		await renderGame();
		expect(screen.getByLabelText('Remove from cart')).toBeInTheDocument();
		expect(screen.getByText('In cart')).toBeInTheDocument();
	});

	it('queues the shop tab the reader switched to', async () => {
		await renderGame({
			offers: [offerA, offerB],
			store_ids: ['shop-a', 'shop-b'],
			cheapest_in_stock: offerB,
			series: [
				{ store_id: 'shop-a', product_id: 5, history: [] },
				{ store_id: 'shop-b', product_id: 6, history: [] }
			]
		});
		await fireEvent.click(screen.getByRole('button', { name: /shop-a ₹/ }));
		await fireEvent.click(screen.getByLabelText('Add to cart'));
		expect(toggle).toHaveBeenCalledWith(
			expect.objectContaining({ product: { id: 5, game_id: 1 } })
		);
	});
});

const queuedRow = {
	id: 9,
	game_id: 1,
	quantity: 1,
	priority: 'normal',
	max_price: null,
	note: null
};

describe('game page cart panel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		queued.value = true;
		row.value = queuedRow;
	});

	it('stays hidden until the game is queued', async () => {
		queued.value = false;
		row.value = null;
		await renderGame();
		expect(screen.queryByText('In your cart')).not.toBeInTheDocument();
	});

	it('sets priority from a pill', async () => {
		await renderGame();
		expect(screen.getByText('In your cart')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Must have' }));
		expect(patch).toHaveBeenCalledWith(1, { priority: 'must' });
	});

	it('marks the current priority as pressed', async () => {
		row.value = { ...queuedRow, priority: 'someday' };
		await renderGame();
		expect(screen.getByRole('button', { name: 'Someday' })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('button', { name: 'Normal' })).toHaveAttribute('aria-pressed', 'false');
	});

	it('changes quantity', async () => {
		row.value = { ...queuedRow, quantity: 2 };
		await renderGame();
		await fireEvent.click(screen.getByLabelText('Increase quantity'));
		expect(patch).toHaveBeenCalledWith(1, { quantity: 3 });
	});

	it('sets and clears the buy-at ceiling', async () => {
		await renderGame();
		await fireEvent.click(screen.getByRole('button', { name: /no limit/ }));
		const field = screen.getByLabelText('Buy at or below');
		await fireEvent.input(field, { target: { value: '1500' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Set' }));
		expect(patch).toHaveBeenCalledWith(1, { max_price: 1500 });
	});

	it('clears the ceiling when the field is emptied', async () => {
		row.value = { ...queuedRow, max_price: 1500 };
		await renderGame();
		await fireEvent.click(screen.getByRole('button', { name: /₹1,500/ }));
		const field = screen.getByLabelText('Buy at or below');
		await fireEvent.input(field, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Set' }));
		expect(patch).toHaveBeenCalledWith(1, { clear_max_price: true });
	});

	it('links through to the cart', async () => {
		await renderGame();
		expect(screen.getByRole('link', { name: 'Open cart' })).toHaveAttribute('href', '/cart');
	});
});
