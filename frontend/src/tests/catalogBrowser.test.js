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

	it('keeps the controls a plain catalog view owns', async () => {
		await renderPage();
		expect(screen.getByRole('heading', { name: 'Browse' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Not merged/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Sort/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Filters/ })).toBeInTheDocument();
	});
});
