import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

const { toggle, queued } = vi.hoisted(() => ({ toggle: vi.fn(), queued: { value: false } }));
vi.mock('$lib/cart.svelte.js', () => ({
	cart: { has: () => queued.value, toggle }
}));

import ProductCard from '$lib/components/ProductCard.svelte';

const item = {
	product: {
		id: 2,
		game_id: 5,
		title: 'Catan',
		store_id: 'shop-a',
		url: 'https://x/p',
		image_url: null
	},
	game: { id: 5, title: 'Catan', hidden: false, bgg_id: null, note: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5
};

describe('ProductCard cart toggle', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		queued.value = false;
	});

	it('offers to queue a game that is not in the cart', async () => {
		render(ProductCard, { props: { item } });
		await fireEvent.click(screen.getByLabelText('Add to cart'));
		expect(toggle).toHaveBeenCalledWith(item);
	});

	it('shows the queued state so the card reads the same everywhere', () => {
		queued.value = true;
		render(ProductCard, { props: { item } });
		expect(screen.getByLabelText('Remove from cart')).toBeInTheDocument();
		expect(screen.getByText('In cart')).toBeInTheDocument();
	});

	it('queuing does not navigate to the game page', async () => {
		const { container } = render(ProductCard, { props: { item } });
		const link = /** @type {HTMLAnchorElement} */ (container.querySelector('a[data-product-card]'));
		const clicked = new MouseEvent('click', { bubbles: true, cancelable: true });
		screen.getByLabelText('Add to cart').dispatchEvent(clicked);
		expect(clicked.defaultPrevented).toBe(true);
		expect(link).toBeTruthy();
	});
});
