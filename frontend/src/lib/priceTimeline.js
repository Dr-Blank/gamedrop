/** @param {any} e */
const stamp = (e) => new Date(e.at).getTime();

/**
 * One event stream for every shop that sells a game.
 *
 * A snapshot that repeats the last one is not an event, so a shop scraped daily
 * at a standing price contributes nothing. Stock that flaps in and out at the
 * same price collapses into a single run — the reader wants the change, not the
 * chatter.
 *
 * @param {Array<{store_id?:string, product_id?:number, history?:Array<{id?:number, price:number, available?:boolean, source?:string, recorded_at:string}>}>} series
 * @param {{hidden?: Set<string>}} opts
 */
export function buildTimeline(series, { hidden = new Set() } = {}) {
	const out = [];
	for (const s of series ?? []) {
		if (hidden.has(s.store_id)) continue;
		const own = [];
		let prev = null;
		for (const snap of s.history ?? []) {
			const available = snap.available !== false;
			const event = {
				store_id: s.store_id ?? null,
				product_id: s.product_id ?? null,
				snapshot_id: snap.id ?? null,
				source: snap.source ?? 'scrape',
				at: snap.recorded_at,
				price: snap.price,
				prevPrice: prev ? prev.price : null,
				available
			};
			if (!prev) own.push({ ...event, kind: 'listed' });
			else if (snap.price !== prev.price)
				own.push({ ...event, kind: snap.price < prev.price ? 'drop' : 'rise' });
			else if (available !== prev.available)
				own.push({ ...event, kind: available ? 'restock' : 'oos' });
			prev = { price: snap.price, available };
		}
		out.push(...collapseFlaps(own));
	}
	return out.sort((a, b) => stamp(b) - stamp(a));
}

/** Fold a run of stock-only changes into one collapsed group. */
function collapseFlaps(events) {
	const out = [];
	let run = [];
	const flush = () => {
		if (run.length > 1) {
			const last = run[run.length - 1];
			out.push({ ...last, kind: 'flaps', count: run.length, since: run[0].at, events: run });
		} else out.push(...run);
		run = [];
	};
	for (const e of events) {
		if (e.kind === 'oos' || e.kind === 'restock') run.push(e);
		else {
			flush();
			out.push(e);
		}
	}
	flush();
	return out;
}
