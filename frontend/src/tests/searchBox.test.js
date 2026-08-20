import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { goto } from '$app/navigation';

const { searchCatalog, toggle } = vi.hoisted(() => ({
	searchCatalog: vi.fn(),
	toggle: vi.fn()
}));
vi.mock('$lib/api.js', async (original) => ({
	...(await original()),
	searchCatalog: (...a) => searchCatalog(...a)
}));
vi.mock('$lib/watchlist.svelte.js', () => ({
	watchlist: { has: () => false, toggle }
}));

import SearchBox from '$lib/components/SearchBox.svelte';

const hit = (id, title) => ({
	product: {
		id,
		game_id: id * 10,
		title,
		store_id: 'satyam',
		url: 'https://x/p',
		image_url: `https://x/${id}.jpg`
	},
	game: { id: id * 10, title },
	latest_price: { price: 610, available: true },
	compare: null
});

const multiShop = (id, title) => ({
	...hit(id, title),
	compare: {
		listing_count: 2,
		store_ids: ['satyam', 'other'],
		cheapest: { product_id: id, store_id: 'satyam', price: 610, available: true },
		cheapest_in_stock: { product_id: id, store_id: 'satyam', price: 610, available: true },
		offers: [
			{ product_id: id, store_id: 'satyam', price: 610, available: true },
			{ product_id: id + 1, store_id: 'other', price: 990, available: true }
		]
	}
});

async function type(value) {
	const input = screen.getByRole('combobox');
	await fireEvent.input(input, { target: { value } });
	return input;
}

describe('SearchBox suggestions', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useRealTimers();
	});

	it('suggests after typing stops, capped to a short list', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan'), hit(2, 'Azul')] });
		render(SearchBox);
		await type('cat');

		await waitFor(() => expect(searchCatalog).toHaveBeenCalledWith('cat', 6));
		expect(await screen.findByText('Catan')).toBeInTheDocument();
		expect(screen.getAllByRole('option')).toHaveLength(2);
	});

	it('waits for a second character before asking the backend', async () => {
		render(SearchBox);
		await type('c');
		await new Promise((r) => setTimeout(r, 250));
		expect(searchCatalog).not.toHaveBeenCalled();
	});

	it('debounces a burst of keystrokes into one request', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		render(SearchBox);
		await type('ca');
		await type('cat');
		await type('cata');

		await waitFor(() => expect(searchCatalog).toHaveBeenCalledOnce());
		expect(searchCatalog).toHaveBeenCalledWith('cata', 6);
	});

	// A slow first request must not paint over the newer one's results.
	it('ignores a stale response that lands last', async () => {
		let resolveSlow;
		searchCatalog
			.mockImplementationOnce(() => new Promise((r) => (resolveSlow = r)))
			.mockResolvedValueOnce({ items: [hit(2, 'Azul')] });

		render(SearchBox);
		await type('ca');
		await waitFor(() => expect(searchCatalog).toHaveBeenCalledOnce());
		await type('azul');
		expect(await screen.findByText('Azul')).toBeInTheDocument();

		resolveSlow({ items: [hit(1, 'Catan')] });
		await new Promise((r) => setTimeout(r, 10));
		expect(screen.queryByText('Catan')).not.toBeInTheDocument();
	});
});

describe('SearchBox row', () => {
	beforeEach(() => vi.clearAllMocks());

	it('shows the game thumbnail', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		const { container } = render(SearchBox);
		await type('cat');
		await screen.findByText('Catan');
		expect(container.querySelector('img')).toHaveAttribute('src', 'https://x/1.jpg');
	});

	it('names the shop when only one sells it', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		render(SearchBox);
		await type('cat');
		expect(await screen.findByText(/satyam/)).toBeInTheDocument();
	});

	it('follows the cursor: hovering a row highlights it and enlarges its picture', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan'), hit(2, 'Azul')] });
		const { container } = render(SearchBox);
		await type('a');
		await type('az');
		await screen.findByText('Azul');

		const [, second] = screen.getAllByRole('option');
		await fireEvent.mouseEnter(second);
		expect(second).toHaveAttribute('aria-selected', 'true');
		expect(container.querySelectorAll('img')[1].parentElement.className).toContain('size-20');

		await fireEvent.mouseLeave(screen.getByRole('listbox'));
		expect(second).toHaveAttribute('aria-selected', 'false');
	});

	it('counts the shops instead of naming one when several sell it', async () => {
		searchCatalog.mockResolvedValue({ items: [multiShop(1, 'Catan')] });
		const { container } = render(SearchBox);
		await type('cat');
		await screen.findByText('Catan');

		expect(screen.getByText(/2 stores/)).toBeInTheDocument();
		expect(screen.queryByText(/satyam ·/)).not.toBeInTheDocument();
		expect(container.querySelectorAll('span[title="satyam"], span[title="other"]')).toHaveLength(2);
	});
});

describe('SearchBox navigation', () => {
	beforeEach(() => vi.clearAllMocks());

	it('goes to the full search page on Enter', async () => {
		render(SearchBox);
		const input = await type('catan');
		await fireEvent.submit(input.closest('form'));
		expect(goto).toHaveBeenCalledWith('/search?q=catan');
	});

	it('opens the highlighted suggestion instead when one is picked', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan'), hit(2, 'Azul')] });
		render(SearchBox);
		const input = await type('cat');
		await screen.findByText('Catan');

		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		await fireEvent.submit(input.closest('form'));
		expect(goto).toHaveBeenCalledWith('/games/20?store=satyam');
	});

	it('offers the full search page at the end of the list', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		render(SearchBox);
		await type('cat');
		await screen.findByText('Catan');

		await fireEvent.click(screen.getByRole('button', { name: /Show all results/ }));
		expect(goto).toHaveBeenCalledWith('/search?q=cat');
	});

	it('closes the list on Escape', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		render(SearchBox);
		const input = await type('cat');
		await screen.findByRole('listbox');

		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('watches a game straight from the list', async () => {
		searchCatalog.mockResolvedValue({ items: [hit(1, 'Catan')] });
		render(SearchBox);
		await type('cat');
		await screen.findByText('Catan');

		await fireEvent.click(screen.getByLabelText('Add to watchlist'));
		expect(toggle).toHaveBeenCalledOnce();
		// Watching keeps the list up — the point is to add several in a row.
		expect(screen.getByRole('listbox')).toBeInTheDocument();
		expect(goto).not.toHaveBeenCalled();
	});
});
