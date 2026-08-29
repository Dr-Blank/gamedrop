import { describe, it, expect } from 'vitest';
import {
	dateModeOf,
	formatRelative,
	isRelative,
	parseRelative,
	todayISO
} from '$lib/dateFilters.js';

describe('relative date values', () => {
	it.each(['now', 'today', '-1d', '-30m', '-1mo', '+2w', 'now-1d', 'NOW - 1D'])(
		'recognises %s as relative',
		(value) => {
			expect(isRelative(value)).toBe(true);
		}
	);

	it.each(['2026-06-01', '', 'yesterday', '-1', '1d', null, 5])(
		'leaves %s to the date picker',
		(value) => {
			expect(isRelative(value)).toBe(false);
		}
	);

	it('splits an offset into the parts the editor shows', () => {
		expect(parseRelative('-3mo')).toEqual({ amount: 3, unit: 'mo', dir: 'ago' });
		expect(parseRelative('+2w')).toEqual({ amount: 2, unit: 'w', dir: 'ahead' });
	});

	it('builds any amount and unit, not only a preset one', () => {
		expect(formatRelative({ amount: 17, unit: 'd', dir: 'ago' })).toBe('-17d');
		expect(formatRelative({ amount: 5, unit: 'h', dir: 'ahead' })).toBe('+5h');
	});

	it('keeps a half-typed amount usable', () => {
		expect(formatRelative({ amount: NaN, unit: 'd', dir: 'ago' })).toBe('-0d');
		expect(formatRelative({ amount: -4, unit: 'd', dir: 'ago' })).toBe('-0d');
	});

	it.each([
		['now', 'now'],
		['today', 'today'],
		['-9d', 'relative'],
		['2026-06-01', 'exact'],
		['', 'exact']
	])('routes %s to the %s editor', (value, mode) => {
		expect(dateModeOf(value)).toBe(mode);
	});
});

describe('the exact-date input', () => {
	it('formats a date for the input', () => {
		expect(todayISO(new Date('2026-06-01T13:45:00Z'))).toBe('2026-06-01');
	});
});
