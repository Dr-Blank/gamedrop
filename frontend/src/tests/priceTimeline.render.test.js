import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PriceTimeline from '$lib/components/PriceTimeline.svelte';
import { buildTimeline } from '$lib/priceTimeline.js';

const snap = (price, available, at) => ({ price, available, recorded_at: at });

const series = [
	{
		store_id: 'shop-a',
		product_id: 1,
		history: [
			snap(2999, true, '2026-08-11T08:00:00'),
			snap(2985, true, '2026-08-14T08:00:00'),
			snap(2985, false, '2026-08-15T08:00:00'),
			snap(2985, true, '2026-08-16T08:00:00'),
			snap(2985, false, '2026-08-17T08:00:00')
		]
	}
];

describe('PriceTimeline', () => {
	it('keeps a flapping stock run collapsed until it is opened', async () => {
		const { user } = renderTimeline();
		expect(screen.getByText(/In and out of stock 3×/)).toBeInTheDocument();
		expect(screen.queryByText('Back in stock')).not.toBeInTheDocument();

		await user.click(screen.getByText(/In and out of stock 3×/));
		expect(screen.getAllByText('Out of stock')).toHaveLength(2);
		expect(screen.getByText('Back in stock')).toBeInTheDocument();
	});

	it('shows the price move and what it replaced', () => {
		renderTimeline();
		// Once as the listing price, once struck through by the drop that replaced it.
		expect(screen.getAllByText('₹2,999')).toHaveLength(2);
		expect(screen.getByText('-0.5%')).toBeInTheDocument();
	});
});

function renderTimeline() {
	const rendered = render(PriceTimeline, { props: { events: buildTimeline(series) } });
	return { ...rendered, user: userEvent() };
}

function userEvent() {
	return {
		click: async (/** @type {Element} */ el) => {
			el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
			await new Promise((r) => setTimeout(r, 0));
		}
	};
}
