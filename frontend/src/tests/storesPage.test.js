import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	getStores: vi.fn(),
	addStore: vi.fn(),
	patchStore: vi.fn(),
	deleteStore: vi.fn(),
	syncStore: vi.fn(),
	syncAllStores: vi.fn(),
	getStoreLogs: vi.fn().mockResolvedValue([]),
	searchProducts: vi.fn().mockResolvedValue([]),
	getStoreTypes: vi.fn().mockResolvedValue([]),
	detectStore: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));

import StoresPage from '../routes/stores/+page.svelte';
import * as api from '$lib/api.js';

function store(overrides = {}) {
	return {
		id: 'shop-a',
		name: 'Shop A',
		type: 'shopify',
		base_url: 'https://www.example-shop.com',
		collection_path: '/collections/board-games',
		enabled: true,
		color: null,
		scrape_config: '{"timeout_sec":30,"request_delay_sec":1,"sync_interval_hours":6}',
		last_synced_at: null,
		last_sync_error: null,
		...overrides
	};
}

function syncLog(overrides = {}) {
	return {
		store_id: 'shop-a',
		started_at: '2026-08-31T06:00:00',
		finished_at: '2026-08-31T06:00:08',
		new_products: 0,
		updated_products: 0,
		price_changes: 2,
		error: null,
		...overrides
	};
}

async function openLogs(logs) {
	api.getStores.mockResolvedValue([store()]);
	api.getStoreLogs.mockResolvedValue(logs);
	render(StoresPage);
	await fireEvent.click(await screen.findByRole('button', { name: 'Logs' }));
	return await screen.findByText(/price changes/);
}

function decodeFilters(href) {
	const f = new URL(href, 'http://localhost').searchParams.get('f');
	return JSON.parse(atob(f));
}

describe('stores page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		api.getStoreLogs.mockResolvedValue([]);
		api.getStoreTypes.mockResolvedValue([]);
	});

	it('links the shop root and the synced category page separately', async () => {
		api.getStores.mockResolvedValue([store()]);
		render(StoresPage);

		const shop = await screen.findByRole('link', { name: /example-shop\.com/ });
		expect(shop).toHaveAttribute('href', 'https://www.example-shop.com');

		const category = screen.getByRole('link', { name: /collections\/board-games/ });
		expect(category).toHaveAttribute(
			'href',
			'https://www.example-shop.com/collections/board-games'
		);
	});

	it('keeps the category link pointing at the store it belongs to', async () => {
		api.getStores.mockResolvedValue([
			store(),
			store({
				id: 'shop-b',
				name: 'Shop B',
				base_url: 'https://other-shop.test',
				collection_path: '/product-category/games/'
			})
		]);
		render(StoresPage);

		const category = await screen.findByRole('link', { name: /product-category\/games/ });
		expect(category).toHaveAttribute('href', 'https://other-shop.test/product-category/games/');
	});

	it('falls back to the base URL when the path cannot be joined', async () => {
		api.getStores.mockResolvedValue([store({ base_url: 'not a url' })]);
		render(StoresPage);

		const links = await screen.findAllByRole('link');
		expect(links.every((a) => a.getAttribute('href'))).toBe(true);
	});

	it('lays the list out without a horizontally scrolling table', async () => {
		api.getStores.mockResolvedValue([store()]);
		const { container } = render(StoresPage);
		await screen.findByRole('link', { name: /example-shop\.com/ });

		expect(container.querySelector('table')).toBeNull();
	});

	it('shows when the last sync ran, in both absolute and relative form', async () => {
		api.getStores.mockResolvedValue([store({ last_synced_at: '2026-08-19T06:00:00' })]);
		render(StoresPage);

		expect(await screen.findByText(/Synced/)).toBeInTheDocument();
	});

	it('links a sync run to the changes that run recorded', async () => {
		const summary = await openLogs([syncLog()]);
		const link = summary.closest('a');

		expect(link.getAttribute('href')).toMatch(/^\/changes\?/);
		expect(decodeFilters(link.getAttribute('href'))).toEqual({
			type: 'group',
			op: 'and',
			conditions: [
				{
					type: 'change_window',
					since: '2026-08-31T06:00:00',
					until: '2026-08-31T06:00:08',
					store_id: 'shop-a'
				},
				{ type: 'condition', field: 'store_id', op: 'eq', value: 'shop-a' }
			]
		});
	});

	it('leaves the window open-ended while a run has not finished', async () => {
		const summary = await openLogs([syncLog({ finished_at: null })]);

		expect(decodeFilters(summary.closest('a').getAttribute('href')).conditions[0]).toEqual({
			type: 'change_window',
			since: '2026-08-31T06:00:00',
			store_id: 'shop-a'
		});
	});

	it('does not link a run that changed nothing', async () => {
		const summary = await openLogs([syncLog({ price_changes: 0 })]);

		expect(summary.closest('a')).toBeNull();
	});

	it('surfaces a sync error instead of a timestamp', async () => {
		api.getStores.mockResolvedValue([store({ last_sync_error: 'fetch failed: timeout' })]);
		render(StoresPage);

		expect(await screen.findByText(/fetch failed: timeout/)).toBeInTheDocument();
	});
});
