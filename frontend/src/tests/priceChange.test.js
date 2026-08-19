import { describe, it, expect } from 'vitest';
import { lastPriceChange, agoLabel } from '$lib/priceChange.js';

const NOW = new Date('2026-08-19T12:00:00Z').getTime();
const snap = (price, iso) => ({ price, recorded_at: iso });

describe('lastPriceChange', () => {
	it('is null without history', () => {
		expect(lastPriceChange([], NOW)).toBeNull();
		expect(lastPriceChange(null, NOW)).toBeNull();
	});

	it('measures from the first snapshot carrying the current price', () => {
		const change = lastPriceChange(
			[
				snap(2985, '2026-08-19T00:30:00Z'),
				snap(2985, '2026-08-16T00:30:00Z'),
				snap(2999, '2026-08-11T00:30:00Z')
			],
			NOW
		);
		expect(change.changed).toBe(true);
		expect(change.at).toBe('2026-08-16T00:30:00Z');
		expect(change.label).toBe('3 days');
	});

	it('falls back to the oldest snapshot when the price never moved', () => {
		const change = lastPriceChange(
			[snap(2985, '2026-08-19T00:00:00Z'), snap(2985, '2026-06-12T00:00:00Z')],
			NOW
		);
		expect(change.changed).toBe(false);
		expect(change.label).toBe('68 days');
	});

	it('reports hours for a change younger than two days', () => {
		const change = lastPriceChange(
			[snap(2500, '2026-08-19T07:00:00Z'), snap(2985, '2026-08-18T07:00:00Z')],
			NOW
		);
		expect(change.label).toBe('5 hours');
	});
});

describe('agoLabel', () => {
	it('keeps sub-hour gaps vague and singular hours singular', () => {
		expect(agoLabel(60_000)).toBe('less than an hour');
		expect(agoLabel(3_700_000)).toBe('1 hour');
		expect(agoLabel(-5)).toBe('less than an hour');
	});
});
