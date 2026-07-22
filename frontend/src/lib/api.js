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
export const bggUnlinked = (page = 1, limit = 20) =>
	req(`/bgg/unlinked?page=${page}&limit=${limit}`);
export const bggRefresh = (bggId) => req(`/bgg/game/${bggId}/refresh`, { method: 'POST' });
export const unlinkBgg = (productId) => req(`/bgg/link/${productId}`, { method: 'DELETE' });

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
export const browseFields = () => req('/browse/fields');
export const browseQuery = (body) =>
	req('/browse/query', { method: 'POST', body: JSON.stringify(body) });

// Shelves
export const getShelves = () => req('/shelves/');
export const shelvesPreview = (limit = 8) => req(`/shelves/preview?limit=${limit}`);
export const createShelf = (body) =>
	req('/shelves/', { method: 'POST', body: JSON.stringify(body) });
export const patchShelf = (id, body) =>
	req(`/shelves/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
export const deleteShelf = (id) => req(`/shelves/${id}`, { method: 'DELETE' });
export const reorderShelves = (ids) =>
	req('/shelves/reorder', { method: 'POST', body: JSON.stringify({ ids }) });

// Home dashboard + discovery feeds
export const getHome = (shelfSize = 12) => req(`/home?shelf_size=${shelfSize}`);
export const feedDrops = (page = 1, limit = 24, inStock = false) =>
	req(`/feed/drops?page=${page}&limit=${limit}${inStock ? '&in_stock=true' : ''}`);
export const feedNew = (page = 1, limit = 24) => req(`/feed/new?page=${page}&limit=${limit}`);
export const feedDiscounts = (page = 1, limit = 24) =>
	req(`/feed/discounts?page=${page}&limit=${limit}`);
export const searchCatalog = (q, limit = 24) =>
	req(`/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// Product overrides
export const setOverride = (productId, body) =>
	req(`/products/${productId}/override`, { method: 'PUT', body: JSON.stringify(body) });
export const clearOverride = (productId) =>
	req(`/products/${productId}/override`, { method: 'DELETE' });

// Hide / unhide
export const getHidden = (page = 1, limit = 48) =>
	req(`/products/hidden?page=${page}&limit=${limit}`);
export const hideProduct = (productId) => req(`/products/${productId}/hide`, { method: 'PUT' });
export const unhideProduct = (productId) =>
	req(`/products/${productId}/hide`, { method: 'DELETE' });

// On-demand image fetch (when a product has no stored image yet)
export const fetchProductImage = (productId) =>
	req(`/products/${productId}/image`, { method: 'POST' });

// App logs
export const getAppLogs = (level, limit = 200) => req(`/logs/?level=${level ?? ''}&limit=${limit}`);
export const getGithubIssueExport = (level = 'ERROR') =>
	fetch(`/api/logs/github-issue?level=${level}`).then((r) => r.text());

// Notifications
export const getNotifications = (limit = 20, offset = 0) =>
	req(`/notifications?limit=${limit}&offset=${offset}`);
export const markNotificationRead = (id) => req(`/notifications/${id}/read`, { method: 'PATCH' });
export const markAllNotificationsRead = () => req('/notifications/read-all', { method: 'POST' });
export const backfillNotifications = () => req('/notifications/backfill', { method: 'POST' });
