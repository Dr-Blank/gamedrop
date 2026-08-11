import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	mergeSuggestions: vi.fn(),
	mergeCandidates: vi.fn(),
	mergeProducts: vi.fn(),
	rejectMerge: vi.fn(),
	fetchProductImage: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import MergeSuggestions from '$lib/components/MergeSuggestions.svelte';
import * as api from '$lib/api.js';

const candidate = {
	score: 120,
	rejected: false,
	item: {
		product: { id: 9, game_id: 4, store_id: 'other-shop', image_url: null },
		game: { id: 4, title: 'Catan' },
		latest_price: { price: 2500 },
		compare: null,
		bgg: null
	}
};

describe('MergeSuggestions', () => {
	beforeEach(() => vi.clearAllMocks());

	it('hands the merge result to onmerged so the page can follow the survivor', async () => {
		api.mergeSuggestions.mockResolvedValue({ items: [candidate] });
		api.mergeProducts.mockResolvedValue({ game: { id: 4 }, listing_count: 2, offers: [] });
		const onmerged = vi.fn();

		render(MergeSuggestions, { props: { productId: 1, onmerged } });
		await fireEvent.click(await screen.findByRole('button', { name: /same game/i }));

		await waitFor(() =>
			expect(onmerged).toHaveBeenCalledWith({
				game: { id: 4 },
				listing_count: 2,
				offers: []
			})
		);
		expect(api.mergeProducts).toHaveBeenCalledWith(1, 9);
	});

	it('offers a manual name search when nothing is suggested', async () => {
		api.mergeSuggestions.mockResolvedValue({ items: [] });
		api.mergeCandidates.mockResolvedValue({ items: [{ ...candidate, rejected: true }] });

		render(MergeSuggestions, { props: { productId: 1 } });
		await fireEvent.click(await screen.findByRole('button', { name: /find it by name/i }));
		const input = screen.getByPlaceholderText(/search other stores/i);
		await fireEvent.input(input, { target: { value: 'catan' } });
		await fireEvent.keyDown(input, { key: 'Enter' });

		await waitFor(() => expect(api.mergeCandidates).toHaveBeenCalledWith(1, 'catan'));
		expect(await screen.findByText(/previously rejected/i)).toBeInTheDocument();
	});
});
