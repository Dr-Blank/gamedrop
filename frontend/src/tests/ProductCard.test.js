import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ProductCard from '$lib/components/ProductCard.svelte';

const item = {
	product: { id: 2, title: 'Catan', store_id: 'satyam', url: 'https://x/p', image_url: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5,
	watchlist: { id: 1, target_price: null }
};

describe('ProductCard (watchlist variant)', () => {
	it('renders title and price', () => {
		render(ProductCard, { props: { item, variant: 'watchlist' } });
		expect(screen.getByText('Catan')).toBeInTheDocument();
		expect(screen.getByText(/610/)).toBeInTheDocument();
	});

	it('fires onremove when the remove button is clicked', async () => {
		const onremove = vi.fn();
		render(ProductCard, { props: { item, variant: 'watchlist', onremove } });
		await fireEvent.click(screen.getByTitle('Remove from watchlist'));
		expect(onremove).toHaveBeenCalledOnce();
	});

	it('shows "any drop" when no target price set', () => {
		render(ProductCard, { props: { item, variant: 'watchlist', target: null } });
		expect(screen.getByText('any drop')).toBeInTheDocument();
	});

	it('browse variant shows "Add to watchlist" when not watched', () => {
		// Real store, empty map -> not watched.
		render(ProductCard, { props: { item, variant: 'browse' } });
		expect(screen.getByLabelText('Add to watchlist')).toBeInTheDocument();
	});
});
