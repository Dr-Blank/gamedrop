import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	mergeQueue: vi.fn(),
	decideMerges: vi.fn(),
	rejectedQueue: vi.fn(),
	getStores: vi.fn().mockResolvedValue([]),
	fetchProductImage: vi.fn().mockResolvedValue({ image_url: null })
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() }
}));
vi.mock('$app/navigation', () => ({ beforeNavigate: vi.fn(), goto: vi.fn() }));

import MergesPage from '../routes/merges/+page.svelte';
import * as api from '$lib/api.js';

function card(id, storeId, title) {
	return {
		product: { id, store_id: storeId, title: `${title} (${storeId})`, image_url: null, url: null },
		game: { id: id * 10, title },
		latest_price: { price: 1000 + id },
		compare: null,
		bgg: null
	};
}

function pair(score, a, b) {
	return { score, left: card(a, 'shop-a', 'Catan'), right: card(b, 'shop-b', 'Catan') };
}

describe('merges page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		api.decideMerges.mockResolvedValue({ merged: 1, rejected: 0, unrejected: 0, skipped: 0 });
		api.fetchProductImage.mockResolvedValue({ image_url: null });
		api.rejectedQueue.mockResolvedValue({ items: [], total: 0 });
	});

	it('fetches images for the pairs coming up, not just the one on screen', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		await screen.findByText('200');

		// All four listings, though only the first pair is rendered.
		await waitFor(() => expect(api.fetchProductImage).toHaveBeenCalledWith(3));
		expect(api.fetchProductImage).toHaveBeenCalledWith(4);
	});

	it('shows the best-scoring pair first', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		expect(await screen.findByText('200')).toBeInTheDocument();
		expect(screen.getByText('2 candidates found')).toBeInTheDocument();
	});

	it('advances to the next pair on one click and sends the merge', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: /same game/i }));

		expect(await screen.findByText('120')).toBeInTheDocument();
		await waitFor(() => expect(api.decideMerges).toHaveBeenCalledWith([[1, 2]], [], []));
	});

	it('records a rejection rather than a merge when the pair is not the same game', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2)], total: 1 });
		render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: /not the same/i }));

		await waitFor(() => expect(api.decideMerges).toHaveBeenCalledWith([], [[1, 2]], []));
	});

	it('skipping decides nothing, moves on, and parks the pair for later', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Skip S' }));

		expect(await screen.findByText('120')).toBeInTheDocument();
		expect(api.decideMerges).not.toHaveBeenCalled();

		await fireEvent.click(screen.getByRole('button', { name: /^skipped/i }));
		expect(await screen.findByText('200')).toBeInTheDocument();
	});

	it('keeps skips across a reload', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		const first = render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Skip S' }));
		await screen.findByText('120');
		first.unmount();

		render(MergesPage);
		// The skipped pair stays out of review and waits under Skipped.
		expect(await screen.findByText('120')).toBeInTheDocument();
		expect(screen.queryByText('200')).not.toBeInTheDocument();
	});

	it('posts unsent decisions by beacon when the page goes away', async () => {
		const beacon = vi.fn(() => true);
		vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon });
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: /not the same/i }));

		window.dispatchEvent(new Event('pagehide'));
		await waitFor(() => expect(beacon).toHaveBeenCalled());
		expect(beacon.mock.calls[0][0]).toBe('/api/games/suggestions/decide');
		vi.unstubAllGlobals();
	});

	it('re-sends decisions left over from a lost flush', async () => {
		localStorage.setItem('gd-merge-pending', JSON.stringify([{ pair: [7, 8], kind: 'reject' }]));
		api.mergeQueue.mockResolvedValue({ items: [], total: 0 });
		render(MergesPage);

		await waitFor(() => expect(api.decideMerges).toHaveBeenCalledWith([], [[7, 8]], []));
	});

	it('undo takes back a decision that has not been sent yet', async () => {
		api.mergeQueue.mockResolvedValue({ items: [pair(200, 1, 2), pair(120, 3, 4)], total: 2 });
		render(MergesPage);
		await fireEvent.click(await screen.findByRole('button', { name: /same game/i }));
		await fireEvent.click(screen.getByRole('button', { name: /^z$/i }));

		expect(await screen.findByText('200')).toBeInTheDocument();
		await waitFor(() => expect(api.decideMerges).not.toHaveBeenCalled());
	});

	it('merges every pair above the threshold in one request', async () => {
		api.mergeQueue.mockResolvedValue({
			items: [pair(200, 1, 2), pair(190, 3, 4), pair(100, 5, 6)],
			total: 3
		});
		vi.stubGlobal(
			'confirm',
			vi.fn(() => true)
		);
		render(MergesPage);
		await screen.findByText('200');

		await fireEvent.click(screen.getByRole('button', { name: /all above score/i }));
		await fireEvent.click(await screen.findByRole('button', { name: /merge all 2/i }));
		await waitFor(() =>
			expect(api.decideMerges).toHaveBeenCalledWith(
				[
					[1, 2],
					[3, 4]
				],
				[],
				[]
			)
		);
		vi.unstubAllGlobals();
	});

	it('says so when there is nothing left to review', async () => {
		api.mergeQueue.mockResolvedValue({ items: [], total: 0 });
		render(MergesPage);
		expect(await screen.findByText(/nothing left to review/i)).toBeInTheDocument();
	});
});
