import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
	dateFormat,
	fmtDate,
	fmtDateOnly,
	fmtDateParts,
	fmtRelative
} from '$lib/dateFormat.svelte.js';

describe('date format preference', () => {
	beforeEach(() => {
		dateFormat.mode = 'auto';
		localStorage.clear();
	});

	it('defaults to auto, which leaves the locale to the browser', () => {
		expect(dateFormat.mode).toBe('auto');
		expect(dateFormat.locale).toBeUndefined();
	});

	it('orders day before month in dmy and after it in mdy', () => {
		const iso = '2026-08-19T12:30:00';
		dateFormat.set('dmy');
		expect(fmtDateOnly(iso)).toBe('19/08/2026');
		dateFormat.set('mdy');
		expect(fmtDateOnly(iso)).toBe('8/19/2026');
		dateFormat.set('ymd');
		expect(fmtDateOnly(iso)).toBe('2026-08-19');
	});

	it('persists the choice and restores it as a locale', () => {
		dateFormat.set('dmy');
		expect(localStorage.getItem('gd-date-format')).toBe('dmy');
		expect(dateFormat.locale).toBe('en-GB');
	});
});

describe('clock preference', () => {
	beforeEach(() => {
		dateFormat.set('dmy');
		dateFormat.setClock('auto');
	});

	const at = (opts) =>
		fmtDateParts('2026-08-19T18:30:00', { hour: 'numeric', minute: '2-digit', ...opts });

	it('defaults to auto and leaves the hour cycle to the locale', () => {
		expect(dateFormat.clock).toBe('auto');
		expect(dateFormat.hour12).toBeUndefined();
	});

	it('forces a 24-hour or 12-hour clock when asked', () => {
		dateFormat.setClock('24h');
		expect(at({ timeZone: 'UTC' })).toBe('18:30');
		dateFormat.setClock('12h');
		expect(at({ timeZone: 'UTC' })).toBe('6:30 pm');
	});

	it('persists the choice', () => {
		dateFormat.setClock('24h');
		expect(localStorage.getItem('gd-clock-format')).toBe('24h');
	});

	it('lets a caller pin the hour cycle regardless of the preference', () => {
		dateFormat.setClock('12h');
		expect(at({ timeZone: 'UTC', hour12: false })).toBe('18:30');
	});
});

describe('timestamp parsing', () => {
	beforeEach(() => dateFormat.set('ymd'));

	it('reads a zoneless backend timestamp as UTC, not local time', () => {
		// Naive UTC from the API must not shift by the viewer's offset.
		const parts = fmtDateParts('2026-08-19T12:30:00', {
			hour: '2-digit',
			minute: '2-digit',
			timeZone: 'UTC',
			hour12: false
		});
		expect(parts).toBe('12:30');
	});

	it('leaves an explicit zone alone', () => {
		const parts = fmtDateParts('2026-08-19T12:30:00+05:30', {
			hour: '2-digit',
			minute: '2-digit',
			timeZone: 'UTC',
			hour12: false
		});
		expect(parts).toBe('07:00');
	});

	it('returns a placeholder for missing or unparseable input', () => {
		expect(fmtDate(null)).toBe('Never');
		expect(fmtDateOnly(undefined)).toBe('Never');
		expect(fmtDateParts('not-a-date', {})).toBe('');
	});
});

describe('relative time', () => {
	beforeEach(() => {
		dateFormat.set('dmy');
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-08-19T12:00:00Z'));
	});
	afterEach(() => vi.useRealTimers());

	const ago = (iso) => fmtRelative(iso);

	it('collapses anything under a minute to "just now"', () => {
		expect(ago('2026-08-19T11:59:30')).toBe('just now');
	});

	it('counts back in the largest unit that fits', () => {
		expect(ago('2026-08-19T09:00:00')).toBe('3 hours ago');
		expect(ago('2026-08-19T11:20:00')).toBe('40 minutes ago');
		expect(ago('2026-08-18T12:00:00')).toBe('yesterday');
		expect(ago('2026-08-05T12:00:00')).toBe('2 weeks ago');
	});

	it('has nothing to say about an empty timestamp', () => {
		expect(ago(null)).toBe('');
	});
});
