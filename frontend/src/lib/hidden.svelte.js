import { getHidden, hideProduct, unhideProduct } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide "hidden games" state. A game the user hides should vanish from every
 * view (browse, drops, new, search, home) and only resurface on the Hidden page,
 * where it can be unhidden. Backend already excludes hidden games from feeds; this
 * store lets already-rendered cards disappear immediately without a refetch.
 */
class HiddenState {
	ready = $state(false);
	/** product ids the user has hidden @type {Set<number>} */
	ids = $state(new Set());

	async load() {
		try {
			const res = await getHidden(1, 500);
			this.ids = new Set(res.items.map((c) => c.product.id));
		} catch {
			// Non-fatal: nothing gets hidden client-side until next load.
		} finally {
			this.ready = true;
		}
	}

	/** @param {number} productId */
	has(productId) {
		return this.ids.has(productId);
	}

	/** @param {any} item a product card ({ product, override, ... }) */
	async hide(item) {
		const pid = item.product.id;
		const title = item.override?.title || item.product.title;
		const next = new Set(this.ids);
		try {
			await hideProduct(pid);
			next.add(pid);
			this.ids = next;
			toast.success(`Hidden ${title}`);
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {number} productId */
	async unhide(productId) {
		const next = new Set(this.ids);
		try {
			await unhideProduct(productId);
			next.delete(productId);
			this.ids = next;
			toast.success('Unhidden');
		} catch (e) {
			toast.error(e.message);
		}
	}
}

export const hidden = new HiddenState();
