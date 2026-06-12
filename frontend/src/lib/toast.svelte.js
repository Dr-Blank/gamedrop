/** @typedef {'success' | 'error' | 'info'} ToastKind */
/** @typedef {{ id: number, kind: ToastKind, message: string }} Toast */

class ToastState {
	/** @type {Toast[]} */
	items = $state([]);
	_id = 0;

	/**
	 * @param {string} message
	 * @param {ToastKind} [kind]
	 * @param {number} [ttl] ms before auto-dismiss
	 */
	push(message, kind = 'info', ttl = 3000) {
		const id = ++this._id;
		this.items.push({ id, kind, message });
		if (ttl > 0) setTimeout(() => this.dismiss(id), ttl);
		return id;
	}

	success(/** @type {string} */ m, ttl) {
		return this.push(m, 'success', ttl);
	}
	error(/** @type {string} */ m, ttl) {
		return this.push(m, 'error', ttl ?? 5000);
	}
	info(/** @type {string} */ m, ttl) {
		return this.push(m, 'info', ttl);
	}

	/** @param {number} id */
	dismiss(id) {
		this.items = this.items.filter((t) => t.id !== id);
	}
}

export const toast = new ToastState();
