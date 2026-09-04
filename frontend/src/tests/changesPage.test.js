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

const WEEK = { type: 'change_window', since: '-1w', until: 'now', include_new: true };

describe('changes page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
		api.browseQuery.mockResolvedValue({ items: [], total: 0 });
	});

	it('opens on the last week of activity, most recent first', async () => {
		await renderPage();
		expect(lastCall()).toMatchObject({
			filters: {
				type: 'group',
				op: 'and',
				conditions: [WEEK]
			},
			sorts: [{ field: 'recorded_at', dir: 'desc' }]
		});
	});

	it('counts listings a shop just added as changes', async () => {
		await renderPage();
		expect(lastCall().filters.conditions[0].include_new).toBe(true);
	});

	it('narrows to a relative window from its header', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last 24h/ }));
		await navigated('goto');

		expect(lastCall().filters.conditions).toEqual([
			{ type: 'change_window', since: '-1d', until: 'now', include_new: true }
		]);
	});

	it('swaps one window for another instead of stacking them', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last 24h/ }));
		await navigated('goto');
		await fireEvent.click(screen.getByRole('button', { name: /Last month/ }));
		await navigated('goto');

		expect(lastCall().filters.conditions).toEqual([
			{ type: 'change_window', since: '-1mo', until: 'now', include_new: true }
		]);
	});

	it('saves a shelf carrying the chosen window', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last 24h/ }));
		await navigated('goto');

		await fireEvent.click(screen.getByRole('button', { name: /Save shelf/ }));
		await fireEvent.input(screen.getByPlaceholderText(/Cheap gateway games/), {
			target: { value: 'Moved today' }
		});
		await fireEvent.click(screen.getByRole('button', { name: /^Save$/ }));

		expect(api.createShelf).toHaveBeenCalledWith(
			expect.objectContaining({
				name: 'Moved today',
				filters: {
					type: 'group',
					op: 'and',
					conditions: [{ type: 'change_window', since: '-1d', until: 'now', include_new: true }]
				}
			})
		);
	});

	it('drops the window when the same one is clicked again', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /Last week/ }));
		await navigated('goto');

		expect(lastCall().filters).toBeNull();
	});

	it('marks the window it opened on as the active quick filter', async () => {
		await renderPage();

		expect(screen.getByRole('button', { name: /Last week/ })).toHaveAttribute(
			'aria-pressed',
			'true'
		);
	});
});
