import { getHidden, hideProduct, unhideProduct } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide "hidden games" state, keyed on the game — hiding covers every shop
 * that sells it. The backend already excludes hidden games from feeds; this
 * store lets a card show its hidden state without a refetch.
 */
class HiddenState {
	ready = $state(false);
	/** game ids the user has hidden @type {Set<number>} */
	ids = $state(new Set());

	async load() {
		try {
			const res = await getHidden();
			this.ids = new Set(res.game_ids);
		} catch {
			// Non-fatal: nothing gets hidden client-side until next load.
		} finally {
			this.ready = true;
		}
	}

	/** @param {number|null|undefined} gameId */
	has(gameId) {
		return gameId != null && this.ids.has(gameId);
	}

	/** @param {any} item a card ({ product, game, ... }) */
	async hide(item) {
		const gameId = item.game?.id ?? item.product?.game_id;
		if (gameId == null) return;
		const next = new Set(this.ids);
		try {
			// Hiding goes through a listing; the backend applies it to the game.
			await hideProduct(item.product.id);
			next.add(gameId);
			this.ids = next;
			toast.success(`Hidden ${item.game?.title || item.product.title}`);
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {any} item a card, or a listing id for the hidden page */
	async unhide(item) {
		const productId = typeof item === 'number' ? item : item.product.id;
		const gameId = typeof item === 'number' ? null : (item.game?.id ?? null);
		const next = new Set(this.ids);
		try {
			const res = await unhideProduct(productId);
			next.delete(gameId ?? res.game_id);
			this.ids = next;
			toast.success('Unhidden');
		} catch (e) {
			toast.error(e.message);
		}
	}
}

export const hidden = new HiddenState();
