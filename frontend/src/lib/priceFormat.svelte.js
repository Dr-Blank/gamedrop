import { browser } from '$app/environment';

const STORAGE_KEY = 'gd-price-rounding';

/** @typedef {'nearest-10' | 'off'} RoundingMode */

const MODES = ['nearest-10', 'off'];

class PriceFormatState {
	/** @type {RoundingMode} */
	mode = $state('nearest-10');

	constructor() {
		if (browser) {
			const saved = /** @type {RoundingMode | null} */ (localStorage.getItem(STORAGE_KEY));
			if (saved && MODES.includes(saved)) this.mode = saved;
		}
	}

	/** @param {RoundingMode} next */
	set(next) {
		this.mode = next;
		if (browser) localStorage.setItem(STORAGE_KEY, next);
	}
}

export const priceFormat = new PriceFormatState();

/**
 * A price ending in 9 leans on the left digit to read smaller than it is;
 * rounding the tail off takes the lean out.
 *
 * @param {number|null|undefined} n
 */
export function roundPrice(n) {
	if (n == null) return n;
	return priceFormat.mode === 'off' ? n : Math.round(n / 10) * 10;
}

/** @param {number|null|undefined} n */
export function inr(n) {
	return inrExact(roundPrice(n));
}

/** For the snapshot log, where each reading is the record and has to stand as taken. */
export function inrExact(/** @type {number|null|undefined} */ n) {
	if (n == null) return '—';
	return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
