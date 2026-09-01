import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PriceTag from '$lib/components/PriceTag.svelte';
import PriceChart from '$lib/components/PriceChart.svelte';
import { priceFormat, roundPrice, inr, inrDelta, inrExact } from '$lib/priceFormat.svelte.js';

// jsdom has no canvas context, so the chart itself is stubbed — the tiles are the subject.
vi.mock('chart.js', () => {
	class Chart {
		static register() {}
		destroy() {}
	}
	return {
		Chart,
		LineController: {},
		LineElement: {},
		PointElement: {},
		LinearScale: {},
		CategoryScale: {},
		Filler: {},
		Tooltip: {}
	};
});

describe('price rounding preference', () => {
	beforeEach(() => {
		priceFormat.mode = 'nearest-10';
		localStorage.clear();
	});

	it('rounds to the nearest ten by default', () => {
		expect(priceFormat.mode).toBe('nearest-10');
		expect(inr(1999)).toBe('₹2,000');
		expect(inr(199)).toBe('₹200');
		expect(inr(1234)).toBe('₹1,230');
		expect(inr(1235)).toBe('₹1,240');
	});

	it('has no price to show for a missing one', () => {
		expect(inr(null)).toBe('—');
		expect(inrExact(undefined)).toBe('—');
		expect(roundPrice(null)).toBe(null);
	});

	it('leaves prices alone when turned off', () => {
		priceFormat.set('off');
		expect(inr(1999)).toBe('₹1,999');
		expect(roundPrice(1234)).toBe(1234);
	});

	it('persists the choice', () => {
		priceFormat.set('off');
		expect(localStorage.getItem('gd-price-rounding')).toBe('off');
	});

	it('keeps inrExact exact in either mode', () => {
		expect(inrExact(1999)).toBe('₹1,999');
		priceFormat.set('off');
		expect(inrExact(1999)).toBe('₹1,999');
	});
});

describe('inrDelta', () => {
	beforeEach(() => {
		priceFormat.mode = 'nearest-10';
	});

	it('signs a move and keeps it exact', () => {
		expect(inrDelta(-1499)).toBe('−₹1,499');
		expect(inrDelta(1499)).toBe('+₹1,499');
		expect(inrDelta(0)).toBe('₹0');
		expect(inrDelta(null)).toBe('—');
	});
});

describe('PriceTag', () => {
	beforeEach(() => {
		priceFormat.mode = 'nearest-10';
	});

	it('rounds the price it quotes', () => {
		render(PriceTag, { props: { price: 1999 } });
		expect(screen.getByText('₹2,000')).toBeInTheDocument();
	});

	it('drops the MRP strike when rounding lands it on the price', () => {
		render(PriceTag, { props: { price: 1999, compareAt: 2000, discountPct: 0.05 } });
		expect(screen.getAllByText('₹2,000')).toHaveLength(1);
	});

	it('keeps the MRP strike when the two still differ', () => {
		render(PriceTag, { props: { price: 610, compareAt: 2000, discountPct: 69.5 } });
		expect(screen.getByText('₹610')).toBeInTheDocument();
		expect(screen.getByText('₹2,000')).toBeInTheDocument();
		expect(screen.getByText('−69.5%')).toBeInTheDocument();
	});
});

describe('PriceChart', () => {
	// One reading keeps the canvas out of it — the tiles render either way.
	const series = [{ store_id: 'a', history: [{ price: 999, recorded_at: '2026-08-01T00:00:00' }] }];

	beforeEach(() => {
		priceFormat.mode = 'nearest-10';
	});

	it('rounds every price it shows', () => {
		render(PriceChart, { props: { series } });
		expect(screen.getAllByText('₹1,000').length).toBeGreaterThan(0);
		expect(screen.queryByText('₹999')).not.toBeInTheDocument();
	});

	it('quotes them exactly once rounding is off', () => {
		priceFormat.mode = 'off';
		render(PriceChart, { props: { series } });
		expect(screen.getAllByText('₹999').length).toBeGreaterThan(0);
	});

	it('states the change in rupees, not in percent', () => {
		HTMLCanvasElement.prototype.getContext = () => ({
			createLinearGradient: () => ({ addColorStop: () => {} })
		});
		const moved = [
			{
				store_id: 'a',
				history: [
					{ price: 1999, recorded_at: '2026-08-01T00:00:00' },
					{ price: 1799, recorded_at: '2026-08-05T00:00:00' }
				]
			}
		];
		render(PriceChart, { props: { series: moved } });
		expect(screen.getByText('−₹200')).toBeInTheDocument();
		expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
	});
});
