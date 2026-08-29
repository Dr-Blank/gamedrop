/**
 * Relative filter values. The backend resolves them at query time, so a saved
 * shelf keeps meaning "the last week" instead of freezing the week it was saved.
 *
 * Vocabulary: `now`, `today` (UTC midnight) and signed offsets like `-3d`.
 */

export const RELATIVE_UNITS = [
	{ value: 'm', label: 'minutes' },
	{ value: 'h', label: 'hours' },
	{ value: 'd', label: 'days' },
	{ value: 'w', label: 'weeks' },
	{ value: 'mo', label: 'months' },
	{ value: 'y', label: 'years' }
];

const OFFSET = /^(?:now)?\s*([+-])\s*(\d+)\s*(mo|[mhdwy])$/;

/** @param {any} value */
function key(value) {
	return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

/** @param {any} value */
export function isRelative(value) {
	const k = key(value);
	return k === 'now' || k === 'today' || OFFSET.test(k);
}

/** Split an offset into the parts the editor shows, or null if it is not one. */
export function parseRelative(value) {
	const match = OFFSET.exec(key(value));
	if (!match) return null;
	const [, sign, amount, unit] = match;
	return { amount: Number(amount), unit, dir: sign === '-' ? 'ago' : 'ahead' };
}

/** @param {{amount: number, unit: string, dir: string}} parts */
export function formatRelative({ amount, unit, dir }) {
	const size = Number.isFinite(Number(amount)) ? Math.max(0, Math.trunc(amount)) : 0;
	return `${dir === 'ahead' ? '+' : '-'}${size}${unit}`;
}

/** Which editor a value wants: an offset, one of the two anchors, or a date. */
export function dateModeOf(value) {
	const k = key(value);
	if (k === 'now') return 'now';
	if (k === 'today') return 'today';
	return parseRelative(k) ? 'relative' : 'exact';
}

/** @param {Date} [at] */
export function todayISO(at = new Date()) {
	return at.toISOString().slice(0, 10);
}
