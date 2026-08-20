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

const { hiddenIds } = vi.hoisted(() => ({ hiddenIds: new Set([5]) }));
vi.mock('$lib/hidden.svelte.js', () => ({
	hidden: { ready: true, has: (id) => hiddenIds.has(id), hide: vi.fn(), unhide: vi.fn() }
}));

import Hidden from '../routes/hidden/+page.svelte';
import * as api from '$lib/api.js';

const card = (gameId, title) => ({
	product: { id: gameId * 10, game_id: gameId, title, store_id: 'satyam', url: 'https://x/p' },
	game: { id: gameId, title, hidden: true, bgg_id: null, note: null },
	latest_price: { price: 610, available: true },
	bgg: null,
	override: null,
	watchlist: null
});

describe('hidden page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
	});

	async function renderPage() {
		render(Hidden);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'load' });
	}

	it('queries hidden games instead of running a feed of its own', async () => {
		api.browseQuery.mockResolvedValue({ items: [card(5, 'Catan')], total: 1 });
		await renderPage();

		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: {
				type: 'group',
				op: 'and',
				conditions: [{ type: 'condition', field: 'hidden', op: 'eq', value: true }]
			},
			hidden_last: false
		});
		expect(await screen.findByText('Catan')).toBeInTheDocument();
		expect(screen.getByText('1 game hidden')).toBeInTheDocument();
	});

	it('skips the divider — every card here is hidden', async () => {
		api.browseQuery.mockResolvedValue({ items: [card(5, 'Catan')], total: 1 });
		await renderPage();

		await screen.findByText('Catan');
		expect(screen.queryByText('Hidden games')).not.toBeInTheDocument();
	});

	// Unhiding is undone on the card, so the row leaves without a refetch.
	it('drops a card once it is no longer hidden', async () => {
		api.browseQuery.mockResolvedValue({
			items: [card(5, 'Catan'), card(9, 'Azul')],
			total: 2
		});
		await renderPage();

		expect(await screen.findByText('Catan')).toBeInTheDocument();
		expect(screen.queryByText('Azul')).not.toBeInTheDocument();
	});
});
