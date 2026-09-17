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
	detectStore: vi.fn(),
	addStoreUrl: vi.fn(),
	patchStoreUrl: vi.fn(),
	deleteStoreUrl: vi.fn(),
	getOrphanListings: vi.fn(),
	cleanupOrphanListings: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));

import StoresPage from '../routes/stores/+page.svelte';
import * as api from '$lib/api.js';

function storeUrl(collection_path, overrides = {}) {
	return { id: 1, collection_path, label: null, enabled: true, ...overrides };
}

function store({ collection_path = '/collections/board-games', ...overrides } = {}) {
	return {
		id: 'shop-a',
		name: 'Shop A',
		type: 'shopify',
		base_url: 'https://www.example-shop.com',
		urls: [storeUrl(collection_path)],
		listing_count: 0,
		enabled: true,
		color: null,
		scrape_config: '{"timeout_sec":30,"request_delay_sec":1,"sync_interval_hours":6}',
		last_synced_at: null,
		last_sync_error: null,
		...overrides
	};
}

function noOrphans() {
	return { listings: 0, games: 0, stores: [] };
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
		api.getOrphanListings.mockResolvedValue(noOrphans());
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
					store_id: 'shop-a',
					include_new: true
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
			store_id: 'shop-a',
			include_new: true
		});
	});

	it('does not link a run that recorded nothing', async () => {
		const summary = await openLogs([syncLog({ price_changes: 0, new_products: 0 })]);

		expect(summary.closest('a')).toBeNull();
	});

	it('links a run that only added listings', async () => {
		const summary = await openLogs([syncLog({ price_changes: 0, new_products: 7 })]);

		expect(summary.closest('a').getAttribute('href')).toMatch(/^\/changes\?/);
	});

	it('surfaces a sync error instead of a timestamp', async () => {
		api.getStores.mockResolvedValue([store({ last_sync_error: 'fetch failed: timeout' })]);
		render(StoresPage);

		expect(await screen.findByText(/fetch failed: timeout/)).toBeInTheDocument();
	});
});

function detection(overrides = {}) {
	return {
		type: 'shopify',
		sample_titles: [],
		base_url: 'https://www.example-shop.com',
		id: 'example-shop',
		id_taken: false,
		name: 'Example Shop',
		collection_path: '/collections/puzzles',
		matches: [],
		...overrides
	};
}

async function check(result, stores = [store()]) {
	api.getStores.mockResolvedValue(stores);
	api.detectStore.mockResolvedValue(result);
	render(StoresPage);
	await screen.findByRole('heading', { name: 'Stores' });
	await fireEvent.input(screen.getByLabelText('Shop URL'), {
		target: { value: 'https://www.example-shop.com/collections/puzzles' }
	});
	await fireEvent.click(screen.getByRole('button', { name: /Check/ }));
	return await screen.findByRole('button', { name: /^Add (store|URL to)/ });
}

describe('a store with several category URLs', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		api.getStoreLogs.mockResolvedValue([]);
		api.getStoreTypes.mockResolvedValue([]);
		api.getOrphanListings.mockResolvedValue(noOrphans());
	});

	it('lists every category URL the store syncs', async () => {
		api.getStores.mockResolvedValue([
			store({
				urls: [storeUrl('/collections/board-games'), storeUrl('/collections/puzzles', { id: 2 })]
			})
		]);
		render(StoresPage);

		expect(await screen.findByRole('link', { name: /collections\/board-games/ })).toHaveAttribute(
			'href',
			'https://www.example-shop.com/collections/board-games'
		);
		expect(screen.getByRole('link', { name: /collections\/puzzles/ })).toHaveAttribute(
			'href',
			'https://www.example-shop.com/collections/puzzles'
		);
	});

	it('adds another category URL to a store already configured', async () => {
		api.getStores.mockResolvedValue([store()]);
		render(StoresPage);

		await fireEvent.click(await screen.findByRole('button', { name: '+ Add category URL' }));
		await fireEvent.input(screen.getByLabelText('New category path for Shop A'), {
			target: { value: '/collections/puzzles' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));

		expect(api.addStoreUrl).toHaveBeenCalledWith('shop-a', {
			collection_path: '/collections/puzzles'
		});
	});

	it('removes one category URL without touching the store', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		api.getStores.mockResolvedValue([store()]);
		render(StoresPage);

		await fireEvent.click(
			await screen.findByRole('button', { name: 'Remove /collections/board-games' })
		);

		expect(api.deleteStoreUrl).toHaveBeenCalledWith('shop-a', 1);
		expect(api.deleteStore).not.toHaveBeenCalled();
	});

	it('pauses a category URL instead of deleting it', async () => {
		api.getStores.mockResolvedValue([store()]);
		render(StoresPage);

		await fireEvent.click(
			await screen.findByRole('button', { name: 'Pause syncing /collections/board-games' })
		);

		expect(api.patchStoreUrl).toHaveBeenCalledWith('shop-a', 1, { enabled: false });
	});
});

describe('checking a pasted URL', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		api.getStoreLogs.mockResolvedValue([]);
		api.getStoreTypes.mockResolvedValue([]);
		api.getOrphanListings.mockResolvedValue(noOrphans());
	});

	it('offers the matching store when the shop is already tracked', async () => {
		await check(detection({ matches: ['shop-a'] }));

		expect(screen.getByLabelText(/Add this URL to an existing store/)).toBeChecked();
		expect(screen.getByLabelText('Store')).toHaveValue('shop-a');
		expect(screen.getByRole('button', { name: 'Add URL to Shop A' })).toBeInTheDocument();
	});

	it('adds the pasted path to the matched store', async () => {
		await check(detection({ matches: ['shop-a'] }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add URL to Shop A' }));

		expect(api.addStoreUrl).toHaveBeenCalledWith('shop-a', {
			collection_path: '/collections/puzzles'
		});
		expect(api.addStore).not.toHaveBeenCalled();
	});

	it('lets the URL go to any store, not only the matched one', async () => {
		const other = store({ id: 'shop-b', name: 'Shop B', base_url: 'https://other-shop.test' });
		await check(detection({ matches: ['shop-a'] }), [store(), other]);

		await fireEvent.change(screen.getByLabelText('Store'), { target: { value: 'shop-b' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add URL to Shop B' }));

		expect(api.addStoreUrl).toHaveBeenCalledWith('shop-b', {
			collection_path: '/collections/puzzles'
		});
	});

	it('will not add a path the chosen store already syncs', async () => {
		await check(detection({ matches: ['shop-a'], collection_path: '/collections/board-games' }));

		expect(screen.getByText(/already syncs this path/)).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Add URL to Shop A/ })).toBeDisabled();
	});

	it('defaults to a new store when no store matches the host', async () => {
		await check(detection());

		expect(screen.getByLabelText(/Add it as a new store/)).toBeChecked();
		expect(screen.getByRole('button', { name: 'Add store' })).toBeInTheDocument();
	});

	it('can still create a separate store for a host already tracked', async () => {
		await check(detection({ matches: ['shop-a'] }));

		await fireEvent.click(screen.getByLabelText(/Add it as a new store/));
		await fireEvent.click(screen.getByRole('button', { name: 'Add store' }));

		expect(api.addStore).toHaveBeenCalledWith(
			expect.objectContaining({ collection_path: '/collections/puzzles' })
		);
		expect(api.addStoreUrl).not.toHaveBeenCalled();
	});
});
