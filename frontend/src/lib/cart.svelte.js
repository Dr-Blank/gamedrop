import { getCart, addToCart, removeFromCart, patchCartItem } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide buy-queue state, keyed on the game — queuing covers every shop that
 * sells it, so the button reads the same on all of them. Loaded once from the
 * layout; the cart page owns the full payload and refreshes this after edits.
 */
class CartState {
	ready = $state(false);
	/** game_id -> queued cart item @type {Map<number, any>} */
	map = $state(new Map());

	async load() {
		try {
			const { items } = await getCart();
			this.map = new Map(items.map((row) => [row.cart.game_id, row.cart]));
		} catch {
			// Non-fatal: cards render as un-queued until the next load.
		} finally {
			this.ready = true;
		}
	}

	get count() {
		return this.map.size;
	}

	/** @param {number|null|undefined} gameId */
	has(gameId) {
		return gameId != null && this.map.has(gameId);
	}

	/** The queued row itself, for panels that edit it where the game is shown. */
	/** @param {number|null|undefined} gameId */
	item(gameId) {
		return (gameId != null && this.map.get(gameId)) || null;
	}

	/**
	 * Queue or unqueue the game this card belongs to. Adding from a card pins
	 * nothing — the row follows the cheapest buyable offer until the cart page
	 * says otherwise.
	 * @param {any} item a card ({ product, game, ... })
	 */
	async toggle(item) {
		const gameId = item.game?.id ?? item.product?.game_id;
		if (gameId == null) return;
		const title = item.game?.title || item.product?.title || 'game';
		const next = new Map(this.map);
		try {
			if (this.map.has(gameId)) {
				await removeFromCart(this.map.get(gameId).id);
				next.delete(gameId);
				this.map = next;
				toast.success(`Removed ${title} from your cart`);
			} else {
				const created = await addToCart({ product_id: item.product.id });
				next.set(gameId, created);
				this.map = next;
				toast.success(`Queued ${title}`);
			}
		} catch (e) {
			toast.error(e.message);
		}
	}

	/**
	 * Edit the queued row from wherever the game is shown.
	 * @param {number} gameId
	 * @param {any} body
	 */
	async patch(gameId, body) {
		const row = this.map.get(gameId);
		if (!row) return;
		try {
			const updated = await patchCartItem(row.id, body);
			const next = new Map(this.map);
			next.set(gameId, updated);
			this.map = next;
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** The cart page edits rows directly; this keeps the card buttons honest. */
	/** @param {any[]} rows */
	sync(rows) {
		this.map = new Map(rows.map((row) => [row.cart.game_id, row.cart]));
		this.ready = true;
	}
}

export const cart = new CartState();
