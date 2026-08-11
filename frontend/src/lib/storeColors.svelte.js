import { getStores } from './api.js';

/**
 * App-wide store accent colours: one hue per shop, so a store looks the same
 * in a chart, a table row and a badge.
 *
 * A store with no saved colour gets a stable one from this palette, picked by
 * hashing its id — new shops are distinguishable without anyone choosing.
 */

/** Readable on both themes at 2px line width and as a small dot. */
export const DEFAULT_PALETTE = [
	'#10b981',
	'#6366f1',
	'#f59e0b',
	'#ec4899',
	'#06b6d4',
	'#a855f7',
	'#ef4444',
	'#84cc16',
	'#0ea5e9',
	'#f97316'
];

/** @param {string} id */
export function defaultColor(id) {
	let hash = 0;
	for (let i = 0; i < (id ?? '').length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
	return DEFAULT_PALETTE[hash % DEFAULT_PALETTE.length];
}

/**
 * Hex → `rgba(r,g,b,a)`, for tints that keep working over either theme's
 * background.
 * @param {string} hex
 * @param {number} alpha
 */
export function tint(hex, alpha) {
	const m = /^#([0-9a-f]{6})$/i.exec(hex ?? '');
	if (!m) return `rgba(120,120,120,${alpha})`;
	const n = parseInt(m[1], 16);
	return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

class StoreColorState {
	ready = $state(false);
	/** store id -> saved hex @type {Map<string, string>} */
	saved = $state(new Map());
	/** store id -> display name @type {Map<string, string>} */
	names = $state(new Map());

	async load() {
		try {
			const stores = await getStores();
			this.saved = new Map(stores.filter((s) => s.color).map((s) => [s.id, s.color]));
			this.names = new Map(stores.map((s) => [s.id, s.name ?? s.id]));
		} catch {
			// Non-fatal: everything falls back to the derived colour.
		} finally {
			this.ready = true;
		}
	}

	/** @param {string|null|undefined} storeId */
	of(storeId) {
		if (!storeId) return DEFAULT_PALETTE[0];
		return this.saved.get(storeId) ?? defaultColor(storeId);
	}

	/** @param {string|null|undefined} storeId */
	name(storeId) {
		if (!storeId) return '';
		return this.names.get(storeId) ?? storeId;
	}

	/**
	 * @param {string} storeId
	 * @param {string|null} hex null restores the derived colour
	 */
	set(storeId, hex) {
		const next = new Map(this.saved);
		if (hex) next.set(storeId, hex);
		else next.delete(storeId);
		this.saved = next;
	}
}

export const storeColors = new StoreColorState();
