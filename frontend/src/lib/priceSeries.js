import { fmtDateParts } from './dateFormat.svelte.js';

/** @param {string|number} at */
export function dayKey(at) {
	return new Date(at).toISOString().slice(0, 10);
}

/**
 * Clip each store's history to a window, keeping the last reading before it.
 *
 * The carried reading is re-dated to the window's first day so the line enters
 * from the edge: its slope answers "was this a rise or a drop?" and its stock
 * state answers "was it even buyable?" without leaving the range.
 *
 * @param {Array<{history?:Array<any>}>} series
 * @param {number} cutoff epoch ms of the window's start
 */
export function clipToWindow(series, cutoff) {
	const from = dayKey(cutoff);
	return (series ?? []).map((s) => {
		const history = s.history ?? [];
		const inside = history.filter((h) => dayKey(h.recorded_at) >= from);
		const before = history.filter((h) => dayKey(h.recorded_at) < from);
		const prior = before[before.length - 1];
		const anchor = prior
			? [
					{
						...prior,
						// Midday UTC so the re-dated anchor lands on `from` whatever the reader's zone.
						recorded_at: `${from}T12:00:00Z`,
						carried: true,
						carried_from: prior.recorded_at
					}
				]
			: [];
		return { ...s, history: [...anchor, ...inside] };
	});
}

/**
 * Align per-store histories onto one day axis.
 *
 * Stores are scraped at different times, so each series is forward-filled from
 * its last known price; days before a store's first snapshot stay null so the
 * line starts where the data does. `real` marks the days a store was actually
 * scraped, so a carried price is never drawn as a data point of its own.
 *
 * `bounds` pins the axis to the viewed window, so a store that never moved
 * still draws a flat line across it instead of collapsing to nothing.
 *
 * @param {Array<{label?:string, store_id?:string, product_id?:number, history?:Array<{price:number, available?:boolean, carried?:boolean, recorded_at:string}>}>} series
 * @param {{from:string, to:string}|null} [bounds] day keys of the axis ends
 */
export function alignSeries(series, bounds = null) {
	let days = [
		...new Set((series ?? []).flatMap((s) => (s.history ?? []).map((h) => dayKey(h.recorded_at))))
	].sort();
	if (bounds) {
		days = [
			...new Set([
				bounds.from,
				...days.filter((d) => d >= bounds.from && d <= bounds.to),
				bounds.to
			])
		].sort();
	}

	const datasets = (series ?? []).map((s) => {
		const byDay = new Map();
		for (const h of s.history ?? []) byDay.set(dayKey(h.recorded_at), h);
		let carry = /** @type {any} */ (null);
		let prevPrice = /** @type {number|null} */ (null);
		const data = /** @type {Array<number|null>} */ ([]);
		const available = /** @type {Array<boolean|null>} */ ([]);
		const real = /** @type {boolean[]} */ ([]);
		const carried = /** @type {boolean[]} */ ([]);
		const entry = /** @type {boolean[]} */ ([]);
		const delta = /** @type {Array<number|null>} */ ([]);
		for (const d of days) {
			const snap = byDay.get(d);
			if (snap) carry = snap;
			const isCarried = !!snap?.carried;
			const isReal = !!snap && !isCarried;
			data.push(carry ? carry.price : null);
			available.push(carry ? carry.available !== false : null);
			real.push(isReal);
			carried.push(isCarried);
			// Nothing before it anywhere in the data: this is the listing appearing.
			entry.push(isReal && prevPrice === null);
			delta.push(isReal && prevPrice !== null ? snap.price - prevPrice : null);
			if (snap) prevPrice = snap.price;
		}
		return {
			label: s.label ?? s.store_id ?? 'Price',
			productId: s.product_id ?? null,
			storeId: s.store_id ?? null,
			data,
			available,
			real,
			carried,
			entry,
			delta
		};
	});

	return { labels: days, datasets };
}

/**
 * Whether a line segment runs over a stretch the shop was selling in.
 *
 * A reading holds until the next one, so a segment takes the stock state of the
 * point it starts at — going out of stock on a day does not dim the days before
 * it.
 *
 * @param {Array<boolean|null>} available
 * @param {number} from index of the segment's first point
 */
export function segmentInStock(available, from) {
	return available[from] !== false;
}

/** @param {string} day */
export function formatDay(day) {
	return fmtDateParts(day, { day: 'numeric', month: 'short' });
}
