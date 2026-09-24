/**
 * Which shop a query is really about, so cards can quote that shop instead of
 * whichever happens to be cheapest.
 *
 * @param {any} filterTree the browse filter tree
 * @param {any[]} sorts the active sort terms
 * @returns {string|null} store id, or null when the query names no shop
 */
export function inferFocusStore(filterTree, sorts = []) {
	return (
		storesInFilter(filterTree)[0] ??
		sorts.find((s) => s.type === 'store_gap' && s.store_a)?.store_a ??
		null
	);
}

/** Every store named anywhere in a filter tree, outermost first. */
function storesInFilter(node) {
	if (!node) return [];
	if (node.type === 'store_compare') return named(node.store_a);
	if (node.type === 'change_window') return named(node.store_id);
	if (node.type === 'condition')
		return node.field === 'store_id' && node.op === 'eq' ? named(node.value) : [];
	// A shop a query excludes is the last one its cards should quote.
	if (node.op === 'not') return [];
	return (node.conditions ?? []).flatMap(storesInFilter);
}

/** A real shop id, or nothing — `*` and a blank stand for no shop in particular. */
function named(storeId) {
	return storeId && storeId !== '*' ? [storeId] : [];
}
