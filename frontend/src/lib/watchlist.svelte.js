import { getWatchlist, addWatchlist, removeWatchlist } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide watchlist state — single source of truth for "is this product
 * watched?" so every ProductCard can render Watch/Unwatch consistently and a
 * toggle on one page is reflected everywhere. Loaded once from the layout.
 */
class WatchlistState {
	ready = $state(false);
	/** product_id -> watchlist item id @type {Map<number, number>} */
	map = $state(new Map());

	async load() {
		try {
			const cards = await getWatchlist();
			this.map = new Map(cards.map((c) => [c.product.id, c.watchlist.id]));
		} catch {
			// Non-fatal: cards just render as un-watched until next load.
		} finally {
			this.ready = true;
		}
	}

	/** @param {number} productId */
	has(productId) {
		return this.map.has(productId);
	}

	/**
	 * Add or remove the product from the watchlist, keeping local state in sync.
	 * @param {any} item a product card ({ product, override, ... })
	 * @param {number|null} targetPrice
	 */
	async toggle(item, targetPrice = null) {
		const pid = item.product.id;
		const title = item.override?.title || item.product.title;
		const next = new Map(this.map);
		try {
			if (this.map.has(pid)) {
				await removeWatchlist(this.map.get(pid));
				next.delete(pid);
				this.map = next;
				toast.success(`Unwatched ${title}`);
			} else {
				const created = await addWatchlist(pid, targetPrice);
				next.set(pid, created.id);
				this.map = next;
				toast.success(`Watching ${title}`);
			}
		} catch (e) {
			toast.error(e.message);
		}
	}
}

export const watchlist = new WatchlistState();
