import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as api from '$lib/api.js';

describe('api client', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => vi.unstubAllGlobals());

	function mockJson(data, ok = true, status = 200) {
		fetch.mockResolvedValue({
			ok,
			status,
			json: async () => data,
			text: async () => JSON.stringify(data)
		});
	}

	it('getWatchlist hits /api/watchlist/ and returns parsed json', async () => {
		mockJson([{ watchlist: { id: 1 } }]);
		const res = await api.getWatchlist();
		expect(fetch).toHaveBeenCalledWith('/api/watchlist/', expect.any(Object));
		expect(res).toEqual([{ watchlist: { id: 1 } }]);
	});

	it('addWatchlist POSTs product_id + target_price', async () => {
		mockJson({ id: 9 });
		await api.addWatchlist(42, 1500);
		const [url, opts] = fetch.mock.calls[0];
		expect(url).toBe('/api/watchlist/');
		expect(opts.method).toBe('POST');
		expect(JSON.parse(opts.body)).toEqual({ product_id: 42, target_price: 1500 });
	});

	it('addWatchlist sends null target when blank', async () => {
		mockJson({ id: 9 });
		await api.addWatchlist(42, '');
		expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
			product_id: 42,
			target_price: null
		});
	});

	it('throws with status + body on non-ok response', async () => {
		mockJson({ detail: 'nope' }, false, 404);
		await expect(api.getWatchlist()).rejects.toThrow(/404/);
	});

	it('getGithubIssueExport passes empty level through (exports all, not just ERROR)', async () => {
		fetch.mockResolvedValue({ ok: true, text: async () => 'logs' });
		await api.getGithubIssueExport('');
		expect(fetch).toHaveBeenCalledWith('/api/logs/github-issue?level=');
	});
});
