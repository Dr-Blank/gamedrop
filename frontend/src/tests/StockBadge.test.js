import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StockBadge from '$lib/components/StockBadge.svelte';

describe('StockBadge', () => {
	it('shows in stock', () => {
		render(StockBadge, { props: { available: true } });
		expect(screen.getByText('In stock')).toBeInTheDocument();
	});

	it('shows pre-order for a buyable pre-order', () => {
		render(StockBadge, { props: { available: true, preorder: true } });
		expect(screen.getByText('Pre-order')).toBeInTheDocument();
	});

	it('ignores pre-order when unavailable', () => {
		render(StockBadge, { props: { available: false, preorder: true } });
		expect(screen.getByText('Out of stock')).toBeInTheDocument();
	});
});
