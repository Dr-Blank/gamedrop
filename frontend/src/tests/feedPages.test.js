import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
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

import Drops from '../routes/drops/+page.svelte';
import New from '../routes/new/+page.svelte';
import * as api from '$lib/api.js';

// SvelteKit re-runs the query through afterNavigate; goto is stubbed here, so
// tests fire that callback themselves.
async function navigated(type = 'load') {
	await afterNavigate.mock.calls.at(-1)[0]({ type });
}

async function renderPage(Component) {
	render(Component);
	await navigated();
}

describe('feed pages', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
		api.browseQuery.mockResolvedValue({ items: [], total: 0 });
	});

	it('drops asks for prices below their last recorded one, steepest first', async () => {
		await renderPage(Drops);
		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: {
				type: 'group',
				op: 'and',
				conditions: [{ type: 'condition', field: 'price_pct_change', op: 'lt', value: 0 }]
			},
			sorts: [{ field: 'price_pct_change', dir: 'asc' }]
		});
	});

	it('drops narrows to buyable ones from its header toggle', async () => {
		await renderPage(Drops);
		await fireEvent.click(screen.getByRole('button', { name: /In stock/ }));
		await navigated('link');

		const filters = api.browseQuery.mock.calls.at(-1)[0].filters;
		expect(filters.conditions).toContainEqual({
			type: 'condition',
			field: 'available',
			op: 'eq',
			value: true
		});
	});

	it('new orders by first seen without filtering anything out', async () => {
		await renderPage(New);
		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: null,
			sorts: [{ field: 'first_seen', dir: 'desc' }]
		});
	});
});
