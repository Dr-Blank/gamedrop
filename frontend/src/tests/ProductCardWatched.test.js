import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

// Force the shared store to report this product as already watched.
const { toggle } = vi.hoisted(() => ({ toggle: vi.fn() }));
vi.mock('$lib/watchlist.svelte.js', () => ({
	watchlist: { has: () => true, toggle }
}));

import ProductCard from '$lib/components/ProductCard.svelte';

const item = {
	product: { id: 2, title: 'Catan', store_id: 'satyam', url: 'https://x/p', image_url: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5
};

describe('ProductCard watch toggle', () => {
	it('shows the Remove (unwatch) affordance when already watched', () => {
		render(ProductCard, { props: { item, variant: 'browse' } });
		// Heart button reflects watched state via its accessible label.
		expect(screen.getByLabelText('Remove from watchlist')).toBeInTheDocument();
		expect(screen.queryByLabelText('Add to watchlist')).not.toBeInTheDocument();
	});

	it('calls store.toggle when the heart is clicked', async () => {
		render(ProductCard, { props: { item, variant: 'browse' } });
		await fireEvent.click(screen.getByLabelText('Remove from watchlist'));
		expect(toggle).toHaveBeenCalledWith(item);
	});

	it('does not render a redundant bottom "Watch" button', () => {
		render(ProductCard, { props: { item, variant: 'browse' } });
		expect(screen.queryByRole('button', { name: /^Watch$/ })).not.toBeInTheDocument();
	});
});
