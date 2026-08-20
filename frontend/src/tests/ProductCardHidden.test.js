import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

// Force the shared store to report this game as hidden.
const { unhide } = vi.hoisted(() => ({ unhide: vi.fn() }));
vi.mock('$lib/hidden.svelte.js', () => ({
	hidden: { has: () => true, hide: vi.fn(), unhide }
}));

import ProductCard from '$lib/components/ProductCard.svelte';

const item = {
	product: {
		id: 2,
		game_id: 5,
		title: 'Catan',
		store_id: 'satyam',
		url: 'https://x/p',
		image_url: null
	},
	game: { id: 5, title: 'Catan', hidden: true, bgg_id: null, note: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5,
	watchlist: { id: 1, target_price: null }
};

describe('ProductCard hidden game', () => {
	// Regression: the card used to render nothing at all, leaving a hole in
	// whatever grid or shelf placed it.
	it('renders the card and flags it as hidden', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByText('Catan')).toBeInTheDocument();
		expect(screen.getByText('Hidden')).toBeInTheDocument();
	});

	it('keeps the store link and unhides from the same eye that hid it', async () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByRole('link', { name: 'Store' })).toBeInTheDocument();
		await fireEvent.click(screen.getByLabelText('Unhide this game'));
		expect(unhide).toHaveBeenCalledOnce();
	});

	// A hidden game can still be watched; the card has to show both so the
	// contradiction is the user's to resolve.
	it('keeps the watch heart and the target chip', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByLabelText('Add to watchlist')).toBeInTheDocument();
		expect(screen.getByTitle('Set target price')).toBeInTheDocument();
	});
});
