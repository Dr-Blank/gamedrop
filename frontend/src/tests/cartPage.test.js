import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	getCart: vi.fn(),
	getPurchased: vi.fn(),
	patchCartItem: vi.fn(),
	removeFromCart: vi.fn(),
	reorderCart: vi.fn(),
	markCartPurchased: vi.fn(),
	unmarkCartPurchased: vi.fn(),
	setCartBudget: vi.fn(),
	addToCart: vi.fn(),
	getStores: vi.fn(() => Promise.resolve([])),
	fetchProductImage: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import Cart from '../routes/cart/+page.svelte';
import * as api from '$lib/api.js';

/** @param {number} id */
function row(id, over = {}) {
	return {
		cart: {
			id,
			game_id: id,
			product_id: null,
			quantity: 1,
			priority: 'normal',
			max_price: null,
			note: null,
			...over.cart
		},
		offer: {
			product_id: id * 10,
			store_id: 's1',
			price: 500,
			available: true,
			url: 'https://s1.test/x',
			...over.offer
		},
		card: {
			product: { id: id * 10, store_id: 's1', image_url: '' },
			game: { id, title: `Game ${id}` },
			bgg: null,
			price_history: [],
			watchlist: null,
			...over.card
		},
		compare: over.compare ?? { offers: [] },
		pinned: over.pinned ?? false,
		price_move: over.price_move ?? null,
		over_max: over.over_max ?? false
	};
}

function payload(rows, summary = {}, switches = []) {
	return {
		items: rows,
		summary: {
			count: rows.length,
			total: rows.length * 500,
			in_stock_total: rows.length * 500,
			unavailable: 0,
			over_max: 0,
			switch_savings: 0,
			budget: null,
			budget_remaining: null,
			cut_index: null,
			by_store: [{ store_id: 's1', count: rows.length, total: rows.length * 500 }],
			...summary
		},
		switches
	};
}

async function renderCart(body) {
	api.getCart.mockResolvedValue(body);
	render(Cart);
	await waitFor(() => expect(api.getCart).toHaveBeenCalled());
	return body;
}

describe('cart page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.getPurchased.mockResolvedValue({ items: [] });
	});

	it('invites you to browse when nothing is queued', async () => {
		await renderCart(payload([]));
		expect(await screen.findByText('Your cart is empty')).toBeInTheDocument();
	});

	it('lists the queue with its total', async () => {
		await renderCart(payload([row(1), row(2)]));
		expect(await screen.findByText('Game 1')).toBeInTheDocument();
		expect(screen.getByText('Game 2')).toBeInTheDocument();
		// The total also names the one shop's basket, so both readings carry it.
		expect(screen.getAllByText('₹1,000').length).toBeGreaterThan(0);
		expect(screen.getByText('2 games')).toBeInTheDocument();
	});

	it('moving a row up saves the new buy order', async () => {
		const body = payload([row(1), row(2)]);
		await renderCart(body);
		api.reorderCart.mockResolvedValue(payload([row(2), row(1)]));

		await fireEvent.click(await screen.findByLabelText('Move Game 2 up'));
		await waitFor(() => expect(api.reorderCart).toHaveBeenCalledWith([2, 1]));
	});

	it('switching the shop pins the chosen listing', async () => {
		const body = payload([
			row(1, {
				compare: {
					offers: [
						{ product_id: 10, store_id: 's1', price: 500, available: true },
						{ product_id: 11, store_id: 's2', price: 400, available: true }
					]
				}
			})
		]);
		await renderCart(body);
		api.patchCartItem.mockResolvedValue({});

		const select = await screen.findByLabelText('Buy from');
		await fireEvent.change(select, { target: { value: '11' } });
		expect(api.patchCartItem).toHaveBeenCalledWith(1, { product_id: 11 });
	});

	it('choosing "cheapest in stock" unpins the row', async () => {
		await renderCart(payload([row(1, { cart: { product_id: 10 }, pinned: true })]));
		api.patchCartItem.mockResolvedValue({});

		await fireEvent.change(await screen.findByLabelText('Buy from'), {
			target: { value: 'auto' }
		});
		expect(api.patchCartItem).toHaveBeenCalledWith(1, { unpin: true });
	});

	it('quantity steps up through the row', async () => {
		await renderCart(payload([row(1)]));
		api.patchCartItem.mockResolvedValue({});

		await fireEvent.click(await screen.findByLabelText('Increase quantity'));
		expect(api.patchCartItem).toHaveBeenCalledWith(1, { quantity: 2 });
	});

	it('marking a row bought takes it out of the queue', async () => {
		await renderCart(payload([row(1)]));
		api.markCartPurchased.mockResolvedValue({});
		api.getCart.mockResolvedValue(payload([]));

		await fireEvent.click(await screen.findByRole('button', { name: /Bought it/ }));
		expect(api.markCartPurchased).toHaveBeenCalledWith(1);
	});

	it('a budget is saved and read back as what is left', async () => {
		await renderCart(payload([row(1)]));
		api.setCartBudget.mockResolvedValue({ budget: 2000 });
		api.getCart.mockResolvedValue(
			payload([row(1)], { budget: 2000, budget_remaining: 1500, cut_index: null })
		);

		await fireEvent.click(await screen.findByRole('button', { name: /Set a budget/ }));
		await fireEvent.input(screen.getByLabelText('Budget'), { target: { value: '2000' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Set' }));

		expect(api.setCartBudget).toHaveBeenCalledWith(2000);
		expect(await screen.findByText('₹1,500 left')).toBeInTheDocument();
	});

	it('marks where the budget runs out in the queue', async () => {
		await renderCart(
			payload([row(1), row(2)], { budget: 700, budget_remaining: -300, cut_index: 1 })
		);
		expect(await screen.findByText(/₹700 budget ends here/)).toBeInTheDocument();
	});

	it('offers to move every pinned row to its cheapest shop', async () => {
		await renderCart(
			payload([row(1, { pinned: true })], { switch_savings: 100 }, [
				{ cart_id: 1, from_store: 's1', to_store: 's2', to_product_id: 11, saves: 100 }
			])
		);
		api.patchCartItem.mockResolvedValue({});

		await fireEvent.click(await screen.findByRole('button', { name: /Save ₹100/ }));
		await waitFor(() => expect(api.patchCartItem).toHaveBeenCalledWith(1, { product_id: 11 }));
	});

	it('narrows to one shop so a single order can be checked out', async () => {
		await renderCart(
			payload([row(1), row(2, { offer: { store_id: 's2' } })], {
				by_store: [
					{ store_id: 's1', count: 1, total: 500 },
					{ store_id: 's2', count: 1, total: 500 }
				]
			})
		);
		await fireEvent.click(await screen.findByRole('button', { name: /^s2/ }));

		expect(screen.queryByText('Game 1')).not.toBeInTheDocument();
		expect(screen.getByText('Game 2')).toBeInTheDocument();
	});

	it('hides what cannot be bought when asked', async () => {
		await renderCart(
			payload([row(1), row(2, { offer: { available: false } })], { unavailable: 1 })
		);
		await fireEvent.click(await screen.findByRole('button', { name: 'In stock' }));

		expect(screen.getByText('Game 1')).toBeInTheDocument();
		expect(screen.queryByText('Game 2')).not.toBeInTheDocument();
	});

	it('flags a row that costs more than its ceiling', async () => {
		await renderCart(
			payload([row(1, { cart: { max_price: 400 }, over_max: true })], { over_max: 1 })
		);
		expect(await screen.findByText(/Over your ₹400 limit/)).toBeInTheDocument();
	});

	it('shows what the price has done since the row was queued', async () => {
		await renderCart(payload([row(1, { price_move: -120 })]));
		expect(await screen.findByText('−₹120')).toBeInTheDocument();
	});

	it('bought rows can be put back in the queue', async () => {
		await renderCart(payload([]));
		api.getPurchased.mockResolvedValue({
			items: [row(9, { cart: { purchased_price: 450 } })]
		});

		await fireEvent.click(await screen.findByRole('button', { name: /Show bought/ }));
		expect(await screen.findByText('Game 9')).toBeInTheDocument();

		api.unmarkCartPurchased.mockResolvedValue({});
		await fireEvent.click(screen.getByRole('button', { name: /Back to cart/ }));
		expect(api.unmarkCartPurchased).toHaveBeenCalledWith(9);
	});
});
