/** @param {string} iso */
function dayKey(iso) {
	return new Date(iso).toISOString().slice(0, 10);
}

/**
 * Align per-store histories onto one day axis.
 *
 * Stores are scraped at different times, so each series is forward-filled from
 * its last known price; days before a store's first snapshot stay null so the
 * line starts where the data does. `real` marks the days a store was actually
 * scraped, so a carried price is never drawn as a data point of its own.
 *
 * @param {Array<{label?:string, store_id?:string, product_id?:number, history?:Array<{price:number, available?:boolean, recorded_at:string}>}>} series
 */
export function alignSeries(series) {
	const days = [
		...new Set((series ?? []).flatMap((s) => (s.history ?? []).map((h) => dayKey(h.recorded_at))))
	].sort();

	const datasets = (series ?? []).map((s) => {
		const byDay = new Map();
		for (const h of s.history ?? []) byDay.set(dayKey(h.recorded_at), h);
		let carry = /** @type {any} */ (null);
		const data = /** @type {Array<number|null>} */ ([]);
		const available = /** @type {Array<boolean|null>} */ ([]);
		const real = /** @type {boolean[]} */ ([]);
		for (const d of days) {
			const snap = byDay.get(d);
			if (snap) carry = snap;
			data.push(carry ? carry.price : null);
			available.push(carry ? carry.available !== false : null);
			real.push(!!snap);
		}
		return {
			label: s.label ?? s.store_id ?? 'Price',
			productId: s.product_id ?? null,
			storeId: s.store_id ?? null,
			data,
			available,
			real
		};
	});

	return { labels: days, datasets };
}

/** @param {string} day */
export function formatDay(day) {
	return new Date(day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
