/**
 * How long the current price has been standing.
 *
 * `changed` is false when every snapshot carries the same price: the price has
 * not moved since tracking started, which is a weaker claim than a real change.
 *
 * @param {Array<{price:number, recorded_at:string}>} history newest first
 * @param {number} now
 */
export function lastPriceChange(history, now = Date.now()) {
	if (!history?.length) return null;
	const current = history[0].price;
	const idx = history.findIndex((s) => s.price !== current);
	const changed = idx > 0;
	const since = changed ? history[idx - 1] : history[history.length - 1];
	const at = new Date(since.recorded_at).getTime();
	if (Number.isNaN(at)) return null;
	const ms = now - at;
	return { changed, at: since.recorded_at, ms, label: agoLabel(ms) };
}

/** @param {number} ms */
export function agoLabel(ms) {
	const hours = Math.floor(Math.max(ms, 0) / 3600000);
	if (hours < 1) return 'less than an hour';
	if (hours < 48) return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
	const days = Math.floor(hours / 24);
	return `${days} days`;
}
