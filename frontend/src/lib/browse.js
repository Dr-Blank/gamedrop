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
