import { describe, it, expect } from 'vitest';
import { buildTimeline } from '$lib/priceTimeline.js';

const snap = (price, available, at) => ({ price, available, recorded_at: at });

describe('buildTimeline', () => {
	it('drops repeats and keeps price moves in both directions', () => {
		const events = buildTimeline([
			{
				store_id: 'a',
				product_id: 1,
				history: [
					snap(2999, true, '2026-08-11T08:00:00'),
					snap(2999, true, '2026-08-12T08:00:00'),
					snap(2985, true, '2026-08-14T08:00:00'),
					snap(3100, true, '2026-08-15T08:00:00')
				]
			}
		]);
		expect(events.map((e) => e.kind)).toEqual(['rise', 'drop', 'listed']);
		expect(events[1].prevPrice).toBe(2999);
		expect(events[1].price).toBe(2985);
	});

	it('collapses a run of stock flapping at a standing price', () => {
		const events = buildTimeline([
			{
				store_id: 'a',
				history: [
					snap(2985, true, '2026-08-11T08:00:00'),
					snap(2985, false, '2026-08-12T08:00:00'),
					snap(2985, true, '2026-08-13T08:00:00'),
					snap(2985, false, '2026-08-14T08:00:00')
				]
			}
		]);
		expect(events.map((e) => e.kind)).toEqual(['flaps', 'listed']);
		expect(events[0].count).toBe(3);
		expect(events[0].since).toBe('2026-08-12T08:00:00');
		expect(events[0].available).toBe(false);
		expect(events[0].events).toHaveLength(3);
	});

	it('keeps a lone stock change on its own', () => {
		const events = buildTimeline([
			{
				store_id: 'a',
				history: [snap(2985, true, '2026-08-11T08:00:00'), snap(2985, false, '2026-08-12T08:00:00')]
			}
		]);
		expect(events.map((e) => e.kind)).toEqual(['oos', 'listed']);
	});

	it('merges every shop onto one newest-first stream, minus hidden ones', () => {
		const series = [
			{
				store_id: 'a',
				history: [snap(2999, true, '2026-08-11T08:00:00'), snap(2985, true, '2026-08-15T08:00:00')]
			},
			{
				store_id: 'b',
				history: [snap(3100, true, '2026-08-12T08:00:00'), snap(3000, true, '2026-08-18T08:00:00')]
			}
		];
		expect(buildTimeline(series).map((e) => [e.store_id, e.kind])).toEqual([
			['b', 'drop'],
			['a', 'drop'],
			['b', 'listed'],
			['a', 'listed']
		]);
		expect(buildTimeline(series, { hidden: new Set(['b']) }).every((e) => e.store_id === 'a')).toBe(
			true
		);
	});

	it('survives empty input', () => {
		expect(buildTimeline(null)).toEqual([]);
		expect(buildTimeline([{ store_id: 'a', history: [] }])).toEqual([]);
	});
});
