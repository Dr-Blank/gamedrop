import { describe, it, expect } from 'vitest';
import { alignSeries, clipToWindow, dayKey } from '$lib/priceSeries.js';

const snap = (price, available, at) => ({ price, available, recorded_at: at });

describe('clipToWindow', () => {
	const series = [
		{
			store_id: 'a',
			history: [
				snap(2490, true, '2026-06-02T00:00:00'),
				snap(2300, true, '2026-07-01T00:00:00'),
				snap(1650, true, '2026-09-15T00:00:00')
			]
		}
	];
	const cutoff = Date.parse('2026-08-11T00:00:00Z');

	it('carries the last reading before the window in as an anchor', () => {
		const [clipped] = clipToWindow(series, cutoff);
		expect(clipped.history).toHaveLength(2);
		expect(clipped.history[0]).toMatchObject({
			price: 2300,
			carried: true,
			carried_from: '2026-07-01T00:00:00'
		});
		expect(dayKey(clipped.history[0].recorded_at)).toBe('2026-08-11');
	});

	it('keeps the anchor stock state so the entering line can be dashed', () => {
		const oos = [{ store_id: 'a', history: [snap(2300, false, '2026-07-01T00:00:00')] }];
		const [clipped] = clipToWindow(oos, cutoff);
		expect(clipped.history[0].available).toBe(false);
	});

	it('adds no anchor when the listing has no history before the window', () => {
		const fresh = [{ store_id: 'a', history: [snap(1650, true, '2026-09-15T00:00:00')] }];
		const [clipped] = clipToWindow(fresh, cutoff);
		expect(clipped.history).toHaveLength(1);
		expect(clipped.history[0].carried).toBeUndefined();
	});
});

describe('alignSeries windowing', () => {
	it('spans the axis to the window so an unmoved price still draws a line', () => {
		const { labels, datasets } = alignSeries(
			[{ store_id: 'a', history: [snap(1650, true, '2026-08-20T00:00:00')] }],
			{ from: '2026-08-11', to: '2026-09-15' }
		);
		expect(labels).toEqual(['2026-08-11', '2026-08-20', '2026-09-15']);
		expect(datasets[0].data).toEqual([null, 1650, 1650]);
	});

	it('drops days outside the bounds', () => {
		const { labels } = alignSeries(
			[
				{
					store_id: 'a',
					history: [
						snap(2490, true, '2026-06-02T00:00:00'),
						snap(1650, true, '2026-08-20T00:00:00')
					]
				}
			],
			{ from: '2026-08-11', to: '2026-09-15' }
		);
		expect(labels).toEqual(['2026-08-11', '2026-08-20', '2026-09-15']);
	});

	it('marks a carried anchor as neither a reading nor a debut', () => {
		const clipped = clipToWindow(
			[
				{
					store_id: 'a',
					history: [
						snap(2490, true, '2026-06-02T00:00:00'),
						snap(1650, true, '2026-08-20T00:00:00')
					]
				}
			],
			Date.parse('2026-08-11T00:00:00Z')
		);
		const { datasets } = alignSeries(clipped, { from: '2026-08-11', to: '2026-09-15' });
		expect(datasets[0].carried).toEqual([true, false, false]);
		expect(datasets[0].real).toEqual([false, true, false]);
		expect(datasets[0].entry).toEqual([false, false, false]);
		// The slope out of the anchor is the drop, so state it in rupees.
		expect(datasets[0].delta).toEqual([null, -840, null]);
	});

	it('flags the first reading of a listing that has nothing before it', () => {
		const { datasets } = alignSeries(
			[
				{
					store_id: 'a',
					history: [
						snap(1650, true, '2026-08-20T00:00:00'),
						snap(1500, true, '2026-09-01T00:00:00')
					]
				}
			],
			{ from: '2026-08-11', to: '2026-09-15' }
		);
		expect(datasets[0].entry).toEqual([false, true, false, false]);
		expect(datasets[0].delta).toEqual([null, null, -150, null]);
	});
});
