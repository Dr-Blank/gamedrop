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

	it('queries without a preset and leaves hidden games out', async () => {
		await renderPage();
		expect(api.browseQuery.mock.calls[0][0]).toMatchObject({
			filters: null,
			include_hidden: false
		});
	});

	it('keeps the controls a plain catalog view owns', async () => {
		await renderPage();
		expect(screen.getByRole('heading', { name: 'Browse' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Not merged/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Sort/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Filters/ })).toBeInTheDocument();
	});
});
