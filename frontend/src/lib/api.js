const BASE = '/api';

async function req(path, options = {}) {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...options.headers },
		...options
	});
	if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
	return res.json();
}

// Stores
export const getStores = () => req('/stores/');
export const addStore = (body) => req('/stores/', { method: 'POST', body: JSON.stringify(body) });
export const patchStore = (id, body) =>
	req(`/stores/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
export const deleteStore = (id) => req(`/stores/${id}`, { method: 'DELETE' });
export const syncStore = (id) => req(`/stores/${id}/sync`, { method: 'POST' });
export const syncAllStores = () => req('/stores/sync-all', { method: 'POST' });
export const getStoreLogs = (id, limit = 20) => req(`/stores/${id}/logs?limit=${limit}`);
export const searchProducts = (storeId, q) =>
	req(`/stores/${storeId}/products?q=${encodeURIComponent(q)}`);

// BGG
export const bggSearch = (q) => req(`/bgg/search?q=${encodeURIComponent(q)}`);
export const bggGame = (id) => req(`/bgg/game/${id}`);
export const linkBgg = (bggId, productId) =>
	req(`/bgg/game/${bggId}/link/${productId}`, { method: 'POST' });

// Prices
export const priceSearch = (q, storeId) =>
	req(`/prices/search?q=${encodeURIComponent(q)}${storeId ? `&store_id=${storeId}` : ''}`);
export const priceHistory = (productId) => req(`/prices/product/${productId}`);

// Watchlist
export const getWatchlist = () => req('/watchlist/');
export const addWatchlist = (productId, targetPrice) =>
	req('/watchlist/', {
		method: 'POST',
		body: JSON.stringify({ product_id: productId, target_price: targetPrice || null })
	});
export const removeWatchlist = (id) => req(`/watchlist/${id}`, { method: 'DELETE' });
export const updateWatchlist = (id, productId, targetPrice) =>
	req(`/watchlist/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ product_id: productId, target_price: targetPrice || null })
	});
export const patchWatchlistItem = (id, body) =>
	req(`/watchlist/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

// Settings
export const getSettings = () => req('/settings/');
export const saveSettings = (body) =>
	req('/settings/', { method: 'PUT', body: JSON.stringify(body) });
export const testBggConnection = () => req('/settings/test/bgg', { method: 'POST' });
export const testNtfyConnection = () => req('/settings/test/ntfy', { method: 'POST' });

// Browse
export const browseStores = () => req('/browse/stores');
export const browse = (params) => req(`/browse?${new URLSearchParams(params)}`);
export const browseSorts = () => req('/browse/sorts');

// Product overrides
export const setOverride = (productId, body) =>
	req(`/products/${productId}/override`, { method: 'PUT', body: JSON.stringify(body) });
export const clearOverride = (productId) =>
	req(`/products/${productId}/override`, { method: 'DELETE' });

// App logs
export const getAppLogs = (level, limit = 200) => req(`/logs/?level=${level ?? ''}&limit=${limit}`);
export const getGithubIssueExport = (level = 'ERROR') =>
	fetch(`/api/logs/github-issue?level=${level}`).then((r) => r.text());
