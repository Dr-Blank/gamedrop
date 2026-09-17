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

function store(overrides = {}) {
	return {
		id: 'shop-a',
		name: 'Shop A',
		type: 'shopify',
		base_url: 'https://www.example-shop.com',
		urls: [{ id: 1, collection_path: '/collections/board-games', label: null, enabled: true }],
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

function decodeFilters(href) {
	const f = new URL(href, 'http://localhost').searchParams.get('f');
	return JSON.parse(atob(f));
}

function reset() {
	vi.clearAllMocks();
	localStorage.clear();
	api.getStoreLogs.mockResolvedValue([]);
	api.getStoreTypes.mockResolvedValue([]);
	api.getOrphanListings.mockResolvedValue(noOrphans());
}

describe('removing a store', () => {
	beforeEach(() => {
		reset();
		api.deleteStore.mockResolvedValue({ ok: true, deleted_listings: 0 });
	});

	async function openConfirm(listing_count = 12) {
		api.getStores.mockResolvedValue([store({ listing_count })]);
		render(StoresPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
	}

	it('asks before removing anything', async () => {
		await openConfirm();

		expect(screen.getByText('Remove "Shop A"?')).toBeInTheDocument();
		expect(api.deleteStore).not.toHaveBeenCalled();
	});

	it('says how many listings the store brought in', async () => {
		await openConfirm();

		expect(screen.getByLabelText(/Also delete its 12 listings/)).not.toBeChecked();
	});

	it('keeps the listings unless they are asked for', async () => {
		await openConfirm();
		await fireEvent.click(screen.getByRole('button', { name: 'Remove store' }));

		expect(api.deleteStore).toHaveBeenCalledWith('shop-a', false);
	});

	it('takes the listings along when the box is ticked', async () => {
		await openConfirm();
		await fireEvent.click(screen.getByLabelText(/Also delete its 12 listings/));
		await fireEvent.click(screen.getByRole('button', { name: 'Remove store and listings' }));

		expect(api.deleteStore).toHaveBeenCalledWith('shop-a', true);
	});

	it('offers nothing to delete when the store has no listings', async () => {
		await openConfirm(0);

		expect(screen.getByText(/no listings to delete/)).toBeInTheDocument();
		expect(screen.queryByLabelText(/Also delete/)).toBeNull();
	});

	it('backs out without calling the API', async () => {
		await openConfirm();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

		expect(api.deleteStore).not.toHaveBeenCalled();
		expect(screen.queryByText('Remove "Shop A"?')).toBeNull();
	});
});

describe('listings left over from removed stores', () => {
	beforeEach(() => {
		reset();
		api.getStores.mockResolvedValue([store()]);
		api.getOrphanListings.mockResolvedValue({
			listings: 793,
			games: 780,
			stores: [{ store_id: 'gone-shop', listings: 793 }]
		});
		api.cleanupOrphanListings.mockResolvedValue({ deleted: 793 });
	});

	it('counts what a cleanup would delete, and names the stores', async () => {
		render(StoresPage);

		expect(await screen.findByText(/793 listings left over/)).toBeInTheDocument();
		expect(screen.getByText(/gone-shop/)).toBeInTheDocument();
	});

	it('links them to browse', async () => {
		render(StoresPage);

		const link = await screen.findByRole('link', { name: /Show them in Browse/ });
		expect(decodeFilters(link.getAttribute('href'))).toEqual({
			type: 'condition',
			field: 'is_orphaned',
			op: 'eq',
			value: true
		});
	});

	it('deletes them on request', async () => {
		render(StoresPage);
		await fireEvent.click(await screen.findByRole('button', { name: /Delete 793 listings/ }));

		expect(api.cleanupOrphanListings).toHaveBeenCalled();
	});

	it('stays out of the way when nothing is orphaned', async () => {
		api.getOrphanListings.mockResolvedValue(noOrphans());
		render(StoresPage);
		await screen.findByRole('heading', { name: 'Stores' });

		expect(screen.queryByText(/left over/)).toBeNull();
	});
});
