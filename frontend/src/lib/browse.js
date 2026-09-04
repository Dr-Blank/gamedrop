/**
 * Build a browse-style URL with base64-encoded filter and sort state.
 * @param {{ filters?: any, sorts?: any[], basePath?: string }} opts
 */
export function browseUrl({ filters = null, sorts = [], basePath = '/browse' } = {}) {
	const params = new URLSearchParams();
	if (filters) params.set('f', btoa(JSON.stringify(filters)));
	if (sorts?.length) params.set('s', btoa(JSON.stringify(sorts)));
	const qs = params.toString();
	return qs ? `${basePath}?${qs}` : basePath;
}

/**
 * The changes one sync run recorded, as a /changes URL. The window is scoped
 * to the store so a shared game moving elsewhere in the same minutes stays out,
 * and counts arrivals — a run that only added listings recorded something too.
 * @param {string} storeId
 * @param {{ started_at: string, finished_at?: string|null }} log
 */
export function syncRunUrl(storeId, { started_at, finished_at }) {
	const window = {
		type: 'change_window',
		since: started_at,
		store_id: storeId,
		include_new: true
	};
	if (finished_at) window.until = finished_at;
	return browseUrl({
		basePath: '/changes',
		filters: {
			type: 'group',
			op: 'and',
			conditions: [window, { type: 'condition', field: 'store_id', op: 'eq', value: storeId }]
		},
		sorts: [{ field: 'recorded_at', dir: 'desc' }]
	});
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
