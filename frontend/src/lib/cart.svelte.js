import { getCart, addToCart, removeFromCart } from './api.js';
import { toast } from './toast.svelte.js';

/**
 * App-wide buy-queue state, keyed on the game — queuing covers every shop that
 * sells it, so the button reads the same on all of them. Loaded once from the
 * layout; the cart page owns the full payload and refreshes this after edits.
 */
class CartState {
	ready = $state(false);
	/** game_id -> cart item id @type {Map<number, number>} */
	map = $state(new Map());

	async load() {
		try {
			const { items } = await getCart();
			this.map = new Map(items.map((row) => [row.cart.game_id, row.cart.id]));
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
				await removeFromCart(this.map.get(gameId));
				next.delete(gameId);
				this.map = next;
				toast.success(`Removed ${title} from your cart`);
			} else {
				const created = await addToCart({ product_id: item.product.id });
				next.set(gameId, created.id);
				this.map = next;
				toast.success(`Queued ${title}`);
			}
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** The cart page edits rows directly; this keeps the card buttons honest. */
	/** @param {any[]} rows */
	sync(rows) {
		this.map = new Map(rows.map((row) => [row.cart.game_id, row.cart.id]));
		this.ready = true;
	}
}

export const cart = new CartState();
