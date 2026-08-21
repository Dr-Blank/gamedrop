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
export const getStoreTypes = () => req('/stores/types');
export const detectStore = (baseUrl) =>
	req('/stores/detect', { method: 'POST', body: JSON.stringify({ base_url: baseUrl }) });
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
export const ignoreSnapshot = (snapshotId) =>
	req(`/prices/snapshot/${snapshotId}/ignore`, { method: 'PUT' });
export const restoreSnapshot = (snapshotId) =>
	req(`/prices/snapshot/${snapshotId}/ignore`, { method: 'DELETE' });
export const addSnapshot = (productId, body) =>
	req(`/prices/product/${productId}/snapshot`, { method: 'POST', body: JSON.stringify(body) });
export const deleteSnapshot = (snapshotId) =>
	req(`/prices/snapshot/${snapshotId}`, { method: 'DELETE' });

// Watchlist
export const getWatchlist = () => req('/watchlist/');
export const addWatchlist = (gameId, targetPrice) =>
	req('/watchlist/', {
		method: 'POST',
		body: JSON.stringify({ game_id: gameId, target_price: targetPrice || null })
	});
export const removeWatchlist = (id) => req(`/watchlist/${id}`, { method: 'DELETE' });
export const updateWatchlist = (id, targetPrice) =>
	req(`/watchlist/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ target_price: targetPrice || null })
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

// Global search
export const searchCatalog = (q, limit = 24) =>
	req(`/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// Product overrides
export const setOverride = (productId, body) =>
	req(`/products/${productId}/override`, { method: 'PUT', body: JSON.stringify(body) });
export const clearOverride = (productId) =>
	req(`/products/${productId}/override`, { method: 'DELETE' });

// Hide / unhide — hiding is a decision about the game, applied via a listing
export const getHidden = () => req('/products/hidden');
export const hideProduct = (productId) => req(`/products/${productId}/hide`, { method: 'PUT' });
export const unhideProduct = (productId) =>
	req(`/products/${productId}/hide`, { method: 'DELETE' });

// On-demand image fetch (when a product has no stored image yet)
export const fetchProductImage = (productId) =>
	req(`/products/${productId}/image`, { method: 'POST' });

// Games (a game = one or more shop listings) and merging
export const getGame = (gameId) => req(`/games/${gameId}`);
export const patchGame = (gameId, body) =>
	req(`/games/${gameId}`, { method: 'PATCH', body: JSON.stringify(body) });
export const gameForListing = (productId) => req(`/games/for-listing/${productId}`);
export const listingDetail = (gameId, productId) => req(`/games/${gameId}/listing/${productId}`);
export const mergeSuggestions = (productId, limit = 6) =>
	req(`/products/${productId}/merge-suggestions?limit=${limit}`);
export const mergeCandidates = (productId, q, limit = 12) =>
	req(`/products/${productId}/merge-candidates?q=${encodeURIComponent(q)}&limit=${limit}`);
export const mergeProducts = (productId, otherProductId) =>
	req(`/products/${productId}/merge`, {
		method: 'POST',
		body: JSON.stringify({ other_product_id: otherProductId })
	});
export const rejectMerge = (productId, otherProductId) =>
	req(`/products/${productId}/reject-merge`, {
		method: 'POST',
		body: JSON.stringify({ other_product_id: otherProductId })
	});
export const unmergeProduct = (productId) =>
	req(`/products/${productId}/game`, { method: 'DELETE' });
export const mergeQueue = (limit = 20, minScore = 0) =>
	req(`/games/suggestions?limit=${limit}&min_score=${minScore}`);
export const decideMerges = (merges, rejects, unrejects = []) =>
	req('/games/suggestions/decide', {
		method: 'POST',
		body: JSON.stringify({ merges, rejects, unrejects })
	});
export const rejectedQueue = (limit = 50, minScore = 0) =>
	req(`/games/suggestions/rejected?limit=${limit}&min_score=${minScore}`);

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
