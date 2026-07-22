/**
 * Keyboard cursor over product grids.
 *
 * Driven off the DOM rather than page state: every grid renders ProductCard,
 * which tags itself `data-product-card` and its buttons `data-action`, so
 * browse, drops, search, watchlist and the home shelves all get this without
 * threading a selection index through each page.
 *
 * The card root is an <a>, so "focused" means DOM focus — Enter, Tab and
 * screen readers keep working with no extra code.
 */

function cards() {
	return /** @type {HTMLElement[]} */ ([...document.querySelectorAll('[data-product-card]')]);
}

/** @returns {HTMLElement | null} */
function focusedCard() {
	const active = document.activeElement;
	return active instanceof HTMLElement ? active.closest('[data-product-card]') : null;
}

/** @param {number} delta */
export function moveCursor(delta) {
	const list = cards();
	if (!list.length) return;

	const current = focusedCard();
	const index = current ? list.indexOf(current) : -1;
	// No cursor yet: `j` starts at the top, `k` at the bottom.
	const next = index < 0 ? (delta > 0 ? 0 : list.length - 1) : index + delta;
	const target = list[Math.min(Math.max(next, 0), list.length - 1)];

	target.focus({ preventScroll: true });
	target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

/** Click a tagged button inside the focused card. @param {string} action */
export function cardAction(action) {
	focusedCard()?.querySelector(`[data-action="${action}"]`)?.click();
}
