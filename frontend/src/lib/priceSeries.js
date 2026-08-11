/** @param {string} iso */
function dayKey(iso) {
	return new Date(iso).toISOString().slice(0, 10);
}

/**
 * Align per-store histories onto one day axis.
 *
 * Stores are scraped at different times, so each series is forward-filled from
 * its last known price; days before a store's first snapshot stay null so the
 * line starts where the data does.
 *
 * @param {Array<{label?:string, store_id?:string, product_id?:number, history?:Array<{price:number, recorded_at:string}>}>} series
 */
export function alignSeries(series) {
	const days = [
		...new Set((series ?? []).flatMap((s) => (s.history ?? []).map((h) => dayKey(h.recorded_at))))
	].sort();

	const datasets = (series ?? []).map((s) => {
		const byDay = new Map();
		for (const h of s.history ?? []) byDay.set(dayKey(h.recorded_at), h.price);
		let carry = /** @type {number|null} */ (null);
		const data = days.map((d) => {
			if (byDay.has(d)) carry = byDay.get(d);
			return carry;
		});
		return {
			label: s.label ?? s.store_id ?? 'Price',
			productId: s.product_id ?? null,
			storeId: s.store_id ?? null,
			data
		};
	});

	return { labels: days, datasets };
}

/** @param {string} day */
export function formatDay(day) {
	return new Date(day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
