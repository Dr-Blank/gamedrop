import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { afterNavigate } from '$app/navigation';

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

vi.mock('$lib/watchlist.svelte.js', () => ({
	watchlist: { ready: true, has: () => true, toggle: vi.fn() }
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
	watchlist: { id: 1, target_price: null }
};

describe('watchlist page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
	});

	// SvelteKit runs the first query from afterNavigate, which is stubbed here.
	async function renderPage() {
		render(Watchlist);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'load' });
	}

	// The page is a browse view with the watch as its preset — no feed of its own.
	it('asks for watched games and keeps hidden ones in view', async () => {
		api.browseQuery.mockResolvedValue({ items: [card], total: 1 });
		await renderPage();

		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: {
				type: 'group',
				op: 'and',
				conditions: [{ type: 'condition', field: 'is_watched', op: 'eq', value: true }]
			},
			hidden_last: true
		});
		expect(await screen.findByText('Catan')).toBeInTheDocument();
		expect(screen.getByText('1 game tracked')).toBeInTheDocument();
	});

	it('shows the empty state when nothing is watched', async () => {
		api.browseQuery.mockResolvedValue({ items: [], total: 0 });
		await renderPage();

		expect(await screen.findByText(/Your watchlist is empty/)).toBeInTheDocument();
	});

	it('leaves out the shelf-saving and merge controls that belong to browse', async () => {
		api.browseQuery.mockResolvedValue({ items: [card], total: 1 });
		await renderPage();

		await screen.findByText('Catan');
		expect(screen.queryByRole('button', { name: /Not merged/ })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Save shelf/ })).not.toBeInTheDocument();
	});
});
