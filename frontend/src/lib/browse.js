/**
 * Build a /browse URL with base64-encoded filter and sort state.
 * @param {{ filters?: any, sorts?: any[] }} opts
 */
export function browseUrl({ filters = null, sorts = [] } = {}) {
	const params = new URLSearchParams();
	if (filters) params.set('f', btoa(JSON.stringify(filters)));
	if (sorts?.length) params.set('s', btoa(JSON.stringify(sorts)));
	const qs = params.toString();
	return qs ? `/browse?${qs}` : '/browse';
}

/** Named presets — the nav and the keyboard shortcuts must point at the same URL. */
export const DROPS_URL = browseUrl({
	filters: { type: 'condition', field: 'price_change', op: 'lt', value: 0 },
	sorts: [
		{ field: 'price_change', dir: 'asc' },
		{ field: 'recorded_at', dir: 'desc' }
	]
});

export const NEW_URL = browseUrl({ sorts: [{ field: 'first_seen', dir: 'desc' }] });
