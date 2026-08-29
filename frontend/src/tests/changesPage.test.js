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

import Changes from '../routes/changes/+page.svelte';
import * as api from '$lib/api.js';

async function navigated(type = 'load') {
	await afterNavigate.mock.calls.at(-1)[0]({ type });
}

async function renderPage() {
	render(Changes);
	await navigated();
}

const lastCall = () => api.browseQuery.mock.calls.at(-1)[0];

describe('changes page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
		api.browseQuery.mockResolvedValue({ items: [], total: 0 });
	});

	it('asks for games that moved at least once, most recent change first', async () => {
		await renderPage();
		expect(lastCall()).toMatchObject({
			filters: {
				type: 'group',
				op: 'and',
				conditions: [{ type: 'change_window' }]
			},
			sorts: [{ field: 'last_change_at', dir: 'desc' }]
		});
	});

	it('narrows to a relative window from its header', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last 24h/ }));
		await navigated('link');

		expect(lastCall().filters.conditions).toContainEqual({
			type: 'change_window',
			since: '-1d',
			until: 'now'
		});
	});

	it('swaps one window for another instead of stacking them', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last 24h/ }));
		await navigated('link');
		await fireEvent.click(screen.getByRole('button', { name: /Last week/ }));
		await navigated('link');

		// The page's own preset rides along unbounded; only the picked window has bounds.
		const windows = lastCall().filters.conditions.filter((c) => c.since);
		expect(windows).toEqual([{ type: 'change_window', since: '-1w', until: 'now' }]);
	});

	it('saves a shelf that keeps both the view and the chosen window', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last week/ }));
		await navigated('link');

		await fireEvent.click(screen.getByRole('button', { name: /Save shelf/ }));
		await fireEvent.input(screen.getByPlaceholderText(/Cheap gateway games/), {
			target: { value: 'Moved this week' }
		});
		await fireEvent.click(screen.getByRole('button', { name: /^Save$/ }));

		expect(api.createShelf).toHaveBeenCalledWith(
			expect.objectContaining({
				name: 'Moved this week',
				filters: {
					type: 'group',
					op: 'and',
					conditions: [
						{ type: 'change_window' },
						{ type: 'change_window', since: '-1w', until: 'now' }
					]
				}
			})
		);
	});

	it('drops the window when the same one is clicked again', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last week/ }));
		await navigated('link');
		await fireEvent.click(screen.getByRole('button', { name: /Last week/ }));
		await navigated('link');

		expect(lastCall().filters.conditions).toEqual([{ type: 'change_window' }]);
	});
});
