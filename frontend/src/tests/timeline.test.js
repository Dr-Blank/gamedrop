import { describe, it, expect } from 'vitest';
import { collapseFlaps, groupEvents, pctMove, valuesAt } from '$lib/timeline.js';

let nextId = 1;
const ev = (game_id, kind, at, extra = {}) => ({
	snapshot_id: nextId++,
	product_id: game_id * 10,
	store_id: 'a',
	game_id,
	kind,
	at,
	price: 100,
	prev_price: 120,
	...extra
});

describe('groupEvents', () => {
	it('puts a game once per day, placed by its newest event', () => {
		const days = groupEvents([
			ev(1, 'drop', '2026-10-16T10:00:00'),
			ev(2, 'rise', '2026-10-16T09:00:00'),
			ev(1, 'listed', '2026-10-16T08:00:00', { store_id: 'b', product_id: 11 }),
			ev(1, 'drop', '2026-10-14T08:00:00')
		]);
		expect(days).toHaveLength(2);
		expect(days[0].groups.map((g) => g.game_id)).toEqual([1, 2]);
		expect(days[0].groups[0].events.map((e) => e.store_id)).toEqual(['a', 'b']);
		expect(days[1].groups.map((g) => g.game_id)).toEqual([1]);
	});

	it('splits a game at the seen line', () => {
		const days = groupEvents(
			[ev(1, 'drop', '2026-10-16T10:00:00'), ev(1, 'rise', '2026-10-16T08:00:00')],
			Date.parse('2026-10-16T09:00:00Z')
		);
		expect(days[0].groups.map((g) => g.seen)).toEqual([false, true]);
	});

	it('folds a later page into groups already shown', () => {
		const first = [ev(1, 'drop', '2026-10-16T10:00:00')];
		const second = [ev(1, 'rise', '2026-10-16T07:00:00', { product_id: 11 })];
		const days = groupEvents([...first, ...second]);
		expect(days[0].groups).toHaveLength(1);
		expect(days[0].groups[0].events).toHaveLength(2);
	});
});

describe('collapseFlaps', () => {
	it('folds one listing’s back-to-back stock flips into one entry', () => {
		const out = collapseFlaps([
			ev(1, 'restock', '2026-10-16T10:00:00'),
			ev(1, 'oos', '2026-10-16T08:00:00'),
			ev(1, 'restock', '2026-10-16T06:00:00')
		]);
		expect(out).toHaveLength(1);
		expect(out[0]).toMatchObject({
			kind: 'flaps',
			count: 3,
			at: '2026-10-16T10:00:00',
			since: '2026-10-16T06:00:00'
		});
	});

	it('keeps each variant’s flips apart', () => {
		const out = collapseFlaps([
			ev(1, 'restock', '2026-10-16T10:00:00', { variant_title: 'DE' }),
			ev(1, 'oos', '2026-10-16T09:00:00', { variant_title: 'EN' })
		]);
		expect(out.map((e) => e.kind)).toEqual(['restock', 'oos']);
	});

	it('keeps price moves and other listings apart from the run', () => {
		const out = collapseFlaps([
			ev(1, 'restock', '2026-10-16T10:00:00'),
			ev(1, 'drop', '2026-10-16T09:00:00'),
			ev(1, 'oos', '2026-10-16T08:00:00'),
			ev(2, 'oos', '2026-10-16T07:00:00')
		]);
		expect(out.map((e) => e.kind)).toEqual(['restock', 'drop', 'oos', 'oos']);
	});
});

describe('pctMove', () => {
	it('measures against the previous price', () => {
		expect(pctMove({ price: 90, prev_price: 100 })).toBeCloseTo(-10);
		expect(pctMove({ price: 90, prev_price: null })).toBeNull();
	});
});

describe('valuesAt', () => {
	it('reads each shop’s standing price at a moment', () => {
		const series = [
			{
				store_id: 'a',
				history: [
					{ price: 100, available: true, recorded_at: '2026-10-01T00:00:00' },
					{ price: 80, available: false, recorded_at: '2026-10-10T00:00:00' }
				]
			},
			{
				store_id: 'b',
				history: [{ price: 90, available: true, recorded_at: '2026-10-12T00:00:00' }]
			}
		];
		const t = Date.parse('2026-10-11T00:00:00Z');
		expect(valuesAt(series, t)).toEqual([{ store_id: 'a', price: 80, available: false }]);
	});
});
