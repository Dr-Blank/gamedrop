import { getWatchlist, addWatchlist, removeWatchlist } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide watchlist state, keyed on the game — watching a game covers every
 * shop that sells it, so a toggle on one shop's card is reflected on all of
 * them. Loaded once from the layout.
 */
class WatchlistState {
	ready = $state(false);
	/** game_id -> watchlist item id @type {Map<number, number>} */
	map = $state(new Map());

	async load() {
		try {
			const cards = await getWatchlist();
			this.map = new Map(cards.map((c) => [c.game.id, c.watchlist.id]));
		} catch {
			// Non-fatal: cards just render as un-watched until next load.
		} finally {
			this.ready = true;
		}
	}

	/** @param {number|null|undefined} gameId */
	has(gameId) {
		return gameId != null && this.map.has(gameId);
	}

	/**
	 * Watch or unwatch the game this card belongs to.
	 * @param {any} item a card ({ product, game, ... })
	 * @param {number|null} targetPrice
	 */
	async toggle(item, targetPrice = null) {
		const gameId = item.game?.id ?? item.product?.game_id;
		if (gameId == null) return;
		const title = item.game?.title || item.product?.title || 'game';
		const next = new Map(this.map);
		try {
			if (this.map.has(gameId)) {
				await removeWatchlist(this.map.get(gameId));
				next.delete(gameId);
				this.map = next;
				toast.success(`Unwatched ${title}`);
			} else {
				const created = await addWatchlist(gameId, targetPrice);
				next.set(gameId, created.id);
				this.map = next;
				toast.success(`Watching ${title}`);
			}
		} catch (e) {
			toast.error(e.message);
		}
	}
}

export const watchlist = new WatchlistState();
