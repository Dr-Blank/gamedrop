import { browser } from '$app/environment';

const STORAGE_KEY = 'gd-date-format';
const CLOCK_STORAGE_KEY = 'gd-clock-format';

/** @typedef {'auto' | 'dmy' | 'mdy' | 'ymd'} DateFormatMode */
/** @typedef {'auto' | '12h' | '24h'} ClockMode */

/** Locales chosen for the order they print, not for the country they name. */
const MODE_LOCALES = {
	dmy: 'en-GB',
	mdy: 'en-US',
	ymd: 'en-CA'
};

/** Backend sends naive UTC; without a zone suffix the browser would read it as local. */
function parse(iso) {
	if (!iso) return null;
	const d =
		typeof iso === 'string' && iso.includes('T') && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(iso)
			? new Date(`${iso}Z`)
			: new Date(iso);
	return Number.isNaN(d.getTime()) ? null : d;
}

class DateFormatState {
	/** @type {DateFormatMode} */
	mode = $state('auto');
	/** @type {ClockMode} */
	clock = $state('auto');

	constructor() {
		if (browser) {
			const saved = /** @type {DateFormatMode | null} */ (localStorage.getItem(STORAGE_KEY));
			if (saved === 'auto' || saved in MODE_LOCALES) this.mode = saved;
			const clock = /** @type {ClockMode | null} */ (localStorage.getItem(CLOCK_STORAGE_KEY));
			if (clock === 'auto' || clock === '12h' || clock === '24h') this.clock = clock;
		}
	}

	/** @param {DateFormatMode} next */
	set(next) {
		this.mode = next;
		if (browser) localStorage.setItem(STORAGE_KEY, next);
	}

	/** @param {ClockMode} next */
	setClock(next) {
		this.clock = next;
		if (browser) localStorage.setItem(CLOCK_STORAGE_KEY, next);
	}

	/** undefined = whatever the browser is set to. */
	get locale() {
		return MODE_LOCALES[this.mode];
	}

	/** undefined leaves the hour cycle to the locale. */
	get hour12() {
		return this.clock === 'auto' ? undefined : this.clock === '12h';
	}
}

export const dateFormat = new DateFormatState();

/** An explicit hour12 in opts wins — callers asking for a fixed shape mean it. */
function withClock(opts) {
	const hour12 = opts.hour12 ?? dateFormat.hour12;
	return hour12 === undefined ? opts : { ...opts, hour12 };
}

/** @param {string|null|undefined} iso */
export function fmtDate(iso) {
	const d = parse(iso);
	if (!d) return 'Never';
	return d.toLocaleString(
		dateFormat.locale,
		withClock({
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		})
	);
}

/** @param {string|null|undefined} iso */
export function fmtDateOnly(iso) {
	const d = parse(iso);
	return d ? d.toLocaleDateString(dateFormat.locale) : 'Never';
}

/**
 * @param {string|null|undefined} iso
 * @param {Intl.DateTimeFormatOptions} opts
 */
export function fmtDateParts(iso, opts) {
	const d = parse(iso);
	return d ? d.toLocaleString(dateFormat.locale, withClock(opts)) : '';
}

const RELATIVE_UNITS = /** @type {const} */ ([
	['year', 31_536_000_000],
	['month', 2_592_000_000],
	['week', 604_800_000],
	['day', 86_400_000],
	['hour', 3_600_000],
	['minute', 60_000]
]);

/** @param {string|null|undefined} iso */
export function fmtRelative(iso) {
	const d = parse(iso);
	if (!d) return '';
	const diff = Date.now() - d.getTime();
	if (Math.abs(diff) < 60_000) return 'just now';
	const rtf = new Intl.RelativeTimeFormat(dateFormat.locale, { numeric: 'auto' });
	for (const [unit, ms] of RELATIVE_UNITS) {
		if (Math.abs(diff) >= ms) return rtf.format(-Math.trunc(diff / ms), unit);
	}
	return 'just now';
}
