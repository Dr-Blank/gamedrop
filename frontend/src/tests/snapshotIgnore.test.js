import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PriceTimeline from '$lib/components/PriceTimeline.svelte';
import AddPriceForm from '$lib/components/AddPriceForm.svelte';
import { buildTimeline } from '$lib/priceTimeline.js';

const snap = (id, price, at, source = 'scrape') => ({
	id,
	price,
	available: true,
	source,
	recorded_at: at
});

const series = [
	{
		store_id: 'shop-a',
		product_id: 1,
		history: [
			snap(10, 2500, '2026-08-11T08:00:00'),
			snap(11, 2699, '2026-08-14T08:00:00'),
			snap(12, 1899, '2026-08-16T08:00:00', 'manual')
		]
	}
];

async function click(el) {
	el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await new Promise((r) => setTimeout(r, 0));
}

describe('buildTimeline snapshot identity', () => {
	it('carries the snapshot id and source onto each event', () => {
		const events = buildTimeline(series);
		expect(events.map((e) => e.snapshot_id)).toEqual([12, 11, 10]);
		expect(events.map((e) => e.source)).toEqual(['manual', 'scrape', 'scrape']);
	});

	it('defaults to scrape when a reading carries no source', () => {
		const events = buildTimeline([
			{ store_id: 'a', product_id: 1, history: [{ price: 10, recorded_at: '2026-08-11T08:00:00' }] }
		]);
		expect(events[0].source).toBe('scrape');
		expect(events[0].snapshot_id).toBeNull();
	});
});

describe('PriceTimeline ignore controls', () => {
	it('hands the ignored reading back by snapshot id', async () => {
		const onignore = vi.fn();
		render(PriceTimeline, { props: { events: buildTimeline(series), onignore } });

		const buttons = screen.getAllByLabelText('Ignore this reading');
		await click(buttons[0]);

		expect(onignore).toHaveBeenCalledOnce();
		expect(onignore.mock.calls[0][0].snapshot_id).toBe(12);
	});

	it('offers delete only on hand-added readings', () => {
		render(PriceTimeline, {
			props: { events: buildTimeline(series), onignore: vi.fn(), ondelete: vi.fn() }
		});
		expect(screen.getAllByLabelText('Ignore this reading')).toHaveLength(3);
		expect(screen.getAllByLabelText('Delete this hand-added reading')).toHaveLength(1);
	});

	it('marks a hand-added reading as such', () => {
		render(PriceTimeline, { props: { events: buildTimeline(series) } });
		expect(screen.getByText('Added by hand')).toBeInTheDocument();
	});

	it('lists ignored readings with a way back', async () => {
		const onrestore = vi.fn();
		render(PriceTimeline, {
			props: {
				events: buildTimeline(series),
				ignored: [{ id: 99, price: 899, source: 'scrape', recorded_at: '2026-06-18T08:00:00' }],
				onrestore
			}
		});

		expect(screen.getByText('₹899')).toBeInTheDocument();
		await click(screen.getByText(/Restore/));
		expect(onrestore.mock.calls[0][0].id).toBe(99);
	});

	it('shows no ignored section when nothing is ignored', () => {
		render(PriceTimeline, { props: { events: buildTimeline(series) } });
		expect(screen.queryByText(/left out of the chart/)).not.toBeInTheDocument();
	});

	it('disables the control for a reading already in flight', () => {
		render(PriceTimeline, {
			props: { events: buildTimeline(series), busy: new Set([12]), onignore: vi.fn() }
		});
		expect(screen.getAllByLabelText('Ignore this reading')[0]).toBeDisabled();
	});
});

describe('AddPriceForm', () => {
	const listings = [{ product_id: 1, store_id: 'shop-a' }];

	async function fill(price, day = '2025-01-15') {
		for (const [selector, value] of [
			['input[type="date"]', day],
			['input[type="number"]', price]
		]) {
			const el = document.querySelector(selector);
			el.value = value;
			el.dispatchEvent(new Event('input', { bubbles: true }));
		}
		await new Promise((r) => setTimeout(r, 0));
	}

	async function submit() {
		document.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true }));
		await new Promise((r) => setTimeout(r, 0));
	}

	it('submits the listing, price and a midday timestamp', async () => {
		const onadd = vi.fn();
		render(AddPriceForm, { props: { listings, onadd } });
		await fill('1499');
		await submit();

		expect(onadd).toHaveBeenCalledOnce();
		expect(onadd.mock.calls[0][0]).toEqual({
			product_id: 1,
			price: 1499,
			recorded_at: '2025-01-15T12:00:00',
			available: true
		});
	});

	it('refuses to submit without a price', async () => {
		const onadd = vi.fn();
		render(AddPriceForm, { props: { listings, onadd } });
		expect(screen.getByText(/Add price/).closest('button')).toBeDisabled();

		await submit();
		expect(onadd).not.toHaveBeenCalled();
	});

	it('clears the price so the next entry starts empty', async () => {
		render(AddPriceForm, { props: { listings, onadd: vi.fn() } });
		await fill('1499');
		await submit();
		expect(document.querySelector('input[type="number"]').value).toBe('');
	});

	it('offers a shop picker only when more than one sells the game', () => {
		render(AddPriceForm, { props: { listings } });
		expect(document.querySelector('select')).toBeNull();
	});

	it('offers a shop picker once a second shop sells it', () => {
		render(AddPriceForm, {
			props: { listings: [...listings, { product_id: 2, store_id: 'shop-b' }] }
		});
		expect(document.querySelectorAll('select option')).toHaveLength(2);
	});
});
