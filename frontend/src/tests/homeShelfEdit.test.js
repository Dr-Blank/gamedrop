import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	shelvesPreview: vi.fn(),
	browseQuery: vi.fn(),
	getShelves: vi.fn(),
	patchShelf: vi.fn(),
	reorderShelves: vi.fn(),
	addWatchlist: vi.fn(),
	removeWatchlist: vi.fn(),
	priceHistory: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import Home from '../routes/+page.svelte';
import * as api from '$lib/api.js';

const shelf = (id, name) => ({
	id,
	name,
	icon: 'Layers',
	filters: null,
	sorts: null,
	built_in: false,
	position: id,
	hidden: false
});

async function renderHome() {
	api.shelvesPreview.mockResolvedValue([
		{ shelf: shelf(1, 'Top Discounts'), items: [] },
		{ shelf: shelf(2, 'New Arrivals'), items: [] }
	]);
	api.browseQuery.mockResolvedValue({ items: [], total: 0 });
	api.getShelves.mockResolvedValue([shelf(1, 'Top Discounts'), shelf(2, 'New Arrivals')]);
	render(Home);
	await screen.findByText('Top Discounts');
}

async function enterEditMode() {
	await fireEvent.click(screen.getByRole('button', { name: /edit shelves/i }));
	await screen.findByRole('button', { name: /done/i });
}

describe('home page shelf editing', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.patchShelf.mockResolvedValue({});
		api.reorderShelves.mockResolvedValue([]);
	});

	it('collapses shelves to reorder rows and loads hidden shelves', async () => {
		await renderHome();
		api.getShelves.mockResolvedValue([
			shelf(1, 'Top Discounts'),
			shelf(2, 'New Arrivals'),
			{ ...shelf(3, 'Back in Stock'), hidden: true }
		]);
		await enterEditMode();

		expect(screen.getByRole('button', { name: 'Move New Arrivals up' })).toBeInTheDocument();
		// Hidden shelves become add-back chips.
		await screen.findByText('Back in Stock');
	});

	it('saves the new order when leaving edit mode', async () => {
		await renderHome();
		await enterEditMode();
		await fireEvent.click(screen.getByRole('button', { name: 'Move New Arrivals up' }));
		await fireEvent.click(screen.getByRole('button', { name: /done/i }));

		await waitFor(() => expect(api.reorderShelves).toHaveBeenCalledWith([2, 1]));
	});

	it('does not save while still reordering', async () => {
		await renderHome();
		await enterEditMode();
		await fireEvent.click(screen.getByRole('button', { name: 'Move New Arrivals up' }));
		expect(api.reorderShelves).not.toHaveBeenCalled();
	});

	it('hides a shelf from edit mode and offers it back as a chip', async () => {
		await renderHome();
		await enterEditMode();
		await fireEvent.click(screen.getByRole('button', { name: 'Remove Top Discounts from home' }));

		await waitFor(() => expect(api.patchShelf).toHaveBeenCalledWith(1, { hidden: true }));
		expect(screen.queryByRole('button', { name: 'Move Top Discounts up' })).toBeNull();
		await screen.findByText('Top Discounts'); // now an add-back chip
	});

	it('restores a hidden shelf from the add panel', async () => {
		await renderHome();
		api.getShelves.mockResolvedValue([
			shelf(1, 'Top Discounts'),
			shelf(2, 'New Arrivals'),
			{ ...shelf(3, 'Back in Stock'), hidden: true }
		]);
		await enterEditMode();
		await fireEvent.click(await screen.findByText('Back in Stock'));

		await waitFor(() => expect(api.patchShelf).toHaveBeenCalledWith(3, { hidden: false }));
		await screen.findByRole('button', { name: 'Move Back in Stock up' });
	});

	it('quick-moves a shelf down from its own menu and saves immediately', async () => {
		await renderHome();
		const menus = screen.getAllByRole('button', { name: 'Shelf options' });
		await fireEvent.click(menus[0]);
		await fireEvent.click(screen.getByRole('menuitem', { name: /move down/i }));

		await waitFor(() => expect(api.reorderShelves).toHaveBeenCalledWith([2, 1]));
	});

	it('hides a shelf from its own menu', async () => {
		await renderHome();
		const menus = screen.getAllByRole('button', { name: 'Shelf options' });
		await fireEvent.click(menus[1]);
		await fireEvent.click(screen.getByRole('menuitem', { name: /hide shelf/i }));

		await waitFor(() => expect(api.patchShelf).toHaveBeenCalledWith(2, { hidden: true }));
	});
});
