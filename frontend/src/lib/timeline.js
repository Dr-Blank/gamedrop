import { parseUtc } from './dateFormat.svelte.js';

export const KINDS = /** @type {const} */ (['drop', 'rise', 'restock', 'oos', 'listed']);

/** @param {string} at */
export const stampOf = (at) => parseUtc(at)?.getTime() ?? 0;

/** Local calendar day, so "Today" ends at the reader's midnight. */
export function localDay(/** @type {string} */ at) {
	const d = parseUtc(at);
	if (!d) return '';
	const pad = (/** @type {number} */ n) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Newest-first events as days of one row per game, split at the seen line.
 * One sync touching five listings should read as one row, not five.
 *
 * @param {Array<any>} events newest first
 * @param {number|null} seenStamp epoch ms of the caught-up line
 * @returns {Array<{day: string, groups: Array<{key: string, game_id: number, at: string, seen: boolean, events: Array<any>}>}>}
 */
export function groupEvents(events, seenStamp = null) {
	/** @type {Map<string, {day: string, groups: Array<any>}>} */
	const days = new Map();
	/** @type {Map<string, any>} */
	const groups = new Map();
	for (const e of events ?? []) {
		const day = localDay(e.at);
		const seen = seenStamp != null && stampOf(e.at) <= seenStamp;
		const key = `${day}:${e.game_id}${seen ? ':seen' : ''}`;
		let group = groups.get(key);
		if (!group) {
			group = { key, game_id: e.game_id, at: e.at, seen, events: [] };
			groups.set(key, group);
			if (!days.has(day)) days.set(day, { day, groups: [] });
			days.get(day)?.groups.push(group);
		}
		group.events.push(e);
	}
	for (const g of groups.values()) g.events = collapseFlaps(g.events);
	return [...days.values()];
}

/** @param {any} e */
const runKey = (e) => `${e.product_id}:${e.variant_title ?? ''}`;

/**
 * Fold one listing variant's back-to-back stock flips into a single entry.
 *
 * @param {Array<any>} events newest first
 */
export function collapseFlaps(events) {
	/** @type {Map<string, Array<any>>} */
	const runs = new Map();
	const out = [];
	for (const e of events) {
		const stock = e.kind === 'oos' || e.kind === 'restock';
		const run = runs.get(runKey(e));
		if (stock && run) {
			run.push(e);
			continue;
		}
		if (stock) {
			const fresh = [e];
			runs.set(runKey(e), fresh);
			out.push(fresh);
		} else {
			runs.delete(runKey(e));
			out.push([e]);
		}
	}
	return out.map((run) =>
		run.length === 1
			? run[0]
			: { ...run[0], kind: 'flaps', count: run.length, since: run[run.length - 1].at }
	);
}

/** @param {{price: number, prev_price: number|null}} e */
export function pctMove(e) {
	if (!e.prev_price) return null;
	return ((e.price - e.prev_price) / e.prev_price) * 100;
}

/**
 * Each shop's price and stock at a moment, read off its step history.
 *
 * @param {Array<{product_id?: number, store_id: string, history: Array<{price: number, available: boolean, recorded_at: string}>}>} series
 * @param {number} t epoch ms
 */
export function valuesAt(series, t) {
	return series.flatMap((s) => {
		let hit = null;
		for (const h of s.history) {
			if (stampOf(h.recorded_at) > t) break;
			hit = h;
		}
		return hit
			? [
					{
						product_id: s.product_id,
						store_id: s.store_id,
						price: hit.price,
						available: hit.available
					}
				]
			: [];
	});
}
