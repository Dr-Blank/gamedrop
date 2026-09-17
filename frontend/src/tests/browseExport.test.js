import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { afterNavigate } from '$app/navigation';

import { toMarkdown, toCsv, csvFilename } from '$lib/exportRows.js';

vi.mock('$lib/api.js', () => ({
	browseFields: vi.fn(),
	browseStores: vi.fn(),
	browseQuery: vi.fn(),
	browseExport: vi.fn(),
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
import { toast } from '$lib/toast.svelte.js';

const row = (over = {}) => ({
	game: 'Catan',
	store: 'Store One',
	price: 300,
	in_stock: true,
	cheapest_in_stock_price: 300,
	cheapest_in_stock_store: 'Store One',
	store_count: 2,
	watched: false,
	in_cart: false,
	owned: false,
	...over
});

describe('export rendering', () => {
	it('copies a four-column markdown table', () => {
		const md = toMarkdown([row(), row({ store: 'Store Two', price: 250, in_stock: false })]);
		expect(md).toBe(
			[
				'| Game | Store | Price | Stock |',
				'| --- | --- | --- | --- |',
				'| Catan | Store One | 300 | in stock |',
				'| Catan | Store Two | 250 | out of stock |'
			].join('\n')
		);
	});

	it('leaves a missing price blank rather than printing null', () => {
		expect(toMarkdown([row({ price: null })])).toContain('| Catan | Store One |  | in stock |');
	});

	it('writes every csv column with booleans spelled out', () => {
		const csv = toCsv([row({ watched: true })]);
		const [head, line] = csv.split('\n');
		expect(head).toBe(
			'game,store,price,in_stock,cheapest_in_stock_price,cheapest_in_stock_store,store_count,watched,in_cart,owned'
		);
		expect(line).toBe('Catan,Store One,300,true,300,Store One,2,true,false,false');
	});

	it('quotes a title containing a comma', () => {
		expect(toCsv([row({ game: 'Catan, 5th Edition' })])).toContain('"Catan, 5th Edition"');
	});

	it('leaves an empty cell for a game nothing has in stock', () => {
		expect(
			toCsv([row({ cheapest_in_stock_price: null, cheapest_in_stock_store: null })])
		).toContain('Catan,Store One,300,true,,,2,false,false,false');
	});

	it('stamps the filename so repeat exports do not collide', () => {
		expect(csvFilename('Price Drops')).toMatch(/^gamedrop-price-drops-\d{4}-\d{2}-\d{2}T.*\.csv$/);
	});
});

describe('browse export buttons', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.browseFields.mockResolvedValue([]);
		api.browseStores.mockResolvedValue([]);
		api.browseQuery.mockResolvedValue({ items: [], total: 3 });
		api.browseExport.mockResolvedValue({ rows: [row()], count: 1 });
		Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
	});

	async function renderPage() {
		render(Browse);
		await afterNavigate.mock.calls.at(-1)[0]({ type: 'load' });
	}

	it('exports the whole query, not the pages already loaded', async () => {
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));

		await waitFor(() => expect(api.browseExport).toHaveBeenCalled());
		const body = api.browseExport.mock.calls[0][0];
		expect(body).not.toHaveProperty('page');
		expect(body).not.toHaveProperty('limit');
		expect(navigator.clipboard.writeText).toHaveBeenCalledWith(toMarkdown([row()]));
	});

	it('says so instead of copying an empty table', async () => {
		api.browseExport.mockResolvedValue({ rows: [], count: 0 });
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));

		await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Nothing to copy'));
		expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
	});

	it('reports a failed copy instead of leaving the button spinning', async () => {
		api.browseExport.mockRejectedValue(new Error('boom'));
		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));

		await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Copy failed: boom'));
	});

	it('downloads the csv under a stamped name', async () => {
		const click = vi.fn();
		const anchor = {
			set href(v) {},
			set download(v) {
				this._name = v;
			},
			click
		};
		const create = vi
			.spyOn(document, 'createElement')
			.mockImplementation((tag) =>
				tag === 'a' ? anchor : document.createElementNS('http://www.w3.org/1999/xhtml', tag)
			);
		URL.createObjectURL = vi.fn(() => 'blob:x');
		URL.revokeObjectURL = vi.fn();

		await renderPage();
		await fireEvent.click(screen.getByRole('button', { name: /csv/i }));

		await waitFor(() => expect(click).toHaveBeenCalled());
		expect(anchor._name).toMatch(/^gamedrop-browse-.*\.csv$/);
		create.mockRestore();
	});
});
