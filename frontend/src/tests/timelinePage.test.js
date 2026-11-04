import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	getTimelineEvents: vi.fn(),
	getTimelineSeen: vi.fn(),
	markTimelineSeen: vi.fn(),
	getStores: vi.fn(),
	fetchProductImage: vi.fn()
}));
vi.mock('$lib/toast.svelte.js', () => ({
	toast: { success: vi.fn(), error: vi.fn() }
}));

import Timeline from '../routes/timeline/+page.svelte';
import * as api from '$lib/api.js';
import { storeColors } from '$lib/storeColors.svelte.js';

const lastParams = () => api.getTimelineEvents.mock.calls.at(-1)[0];

const BODY = {
	events: [
		{
			snapshot_id: 2,
			product_id: 20,
			game_id: 7,
			store_id: 'b',
			kind: 'drop',
			at: new Date().toISOString().replace('Z', ''),
			price: 800,
			prev_price: 1000,
			available: true,
			prev_available: true
		}
	],
	games: { 7: { game_id: 7, title: 'Ark Nova', image_url: null, series: [] } },
	next_cursor: null
};

describe('timeline page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		storeColors.names = new Map([
			['a', 'Shop A'],
			['b', 'Shop B']
		]);
		api.getTimelineEvents.mockResolvedValue(BODY);
		api.getTimelineSeen.mockResolvedValue({ seen_at: null });
	});

	it('opens on a week of every kind across every shop', async () => {
		render(Timeline);
		await waitFor(() => expect(api.getTimelineEvents).toHaveBeenCalled());
		expect(lastParams()).toMatchObject({ stores: '', kinds: '', before: null });
		const weekAgo = Date.now() - 7 * 86_400_000;
		expect(Math.abs(Date.parse(lastParams().since) - weekAgo)).toBeLessThan(60_000);
	});

	it('shows each change with the shop that made it and the move', async () => {
		render(Timeline);
		expect(await screen.findByText('Ark Nova')).toBeInTheDocument();
		expect(screen.getByText('Today')).toBeInTheDocument();
		expect(screen.getByText(/−₹200 · -20.0%/)).toBeInTheDocument();
	});

	it('narrows to the chosen shops, kinds and window', async () => {
		render(Timeline);
		await screen.findByText('Ark Nova');
		await fireEvent.click(screen.getByRole('button', { name: 'Shop A' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Shop B' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Drops' }));
		await fireEvent.click(screen.getByRole('button', { name: '24h' }));
		expect(lastParams()).toMatchObject({ stores: 'a,b', kinds: 'drop' });
		const dayAgo = Date.now() - 86_400_000;
		expect(Math.abs(Date.parse(lastParams().since) - dayAgo)).toBeLessThan(60_000);
	});

	it('pages through the window it opened on', async () => {
		let fire = () => {};
		const original = globalThis.IntersectionObserver;
		vi.stubGlobal(
			'IntersectionObserver',
			class {
				constructor(cb) {
					fire = () => cb([{ isIntersecting: true }]);
				}
				observe() {}
				unobserve() {}
				disconnect() {}
			}
		);
		api.getTimelineEvents
			.mockResolvedValueOnce({ ...BODY, next_cursor: 'c1' })
			.mockResolvedValueOnce({
				...BODY,
				events: [{ ...BODY.events[0], snapshot_id: 1 }]
			});
		render(Timeline);
		await screen.findByText('Ark Nova');
		const first = lastParams();
		await new Promise((r) => setTimeout(r, 20));
		fire();
		await waitFor(() => expect(lastParams().before).toBe('c1'));
		expect(lastParams().since).toBe(first.since);
		vi.stubGlobal('IntersectionObserver', original);
	});

	it('drops the old rows when a filter change fails to load', async () => {
		render(Timeline);
		await screen.findByText('Ark Nova');
		api.getTimelineEvents.mockRejectedValueOnce(new Error('boom'));
		await fireEvent.click(screen.getByRole('button', { name: 'Rises' }));
		await waitFor(() => expect(screen.queryByText('Ark Nova')).not.toBeInTheDocument());
	});

	it('remembers the filters for the next visit', async () => {
		render(Timeline);
		await screen.findByText('Ark Nova');
		await fireEvent.click(screen.getByRole('button', { name: 'Watchlist' }));
		expect(JSON.parse(localStorage.getItem('gd-timeline-filters') ?? '{}').watchlist).toBe(true);
	});

	it('brings hidden games in on demand, without remembering it', async () => {
		render(Timeline);
		await screen.findByText('Ark Nova');
		expect(lastParams().include_hidden).toBe(false);
		api.getTimelineEvents.mockResolvedValue({
			...BODY,
			games: { 7: { ...BODY.games[7], hidden: true } }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Hidden' }));
		expect(lastParams().include_hidden).toBe(true);
		expect(await screen.findByText('hidden')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
		await fireEvent.click(screen.getByRole('button', { name: 'Watchlist' }));
		const saved = JSON.parse(localStorage.getItem('gd-timeline-filters') ?? '{}');
		expect(saved.watchlist).toBe(true);
		expect(Object.keys(saved).some((k) => /hidden/i.test(k))).toBe(false);
		api.getTimelineEvents.mockResolvedValue(BODY);
		await fireEvent.click(screen.getByRole('button', { name: 'Watchlist' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Hidden' }));
		expect(lastParams().include_hidden).toBe(false);
		await waitFor(() => expect(screen.queryByText('hidden')).not.toBeInTheDocument());
	});

	describe('caught up', () => {
		const at = (hoursAgo) =>
			new Date(Date.now() - hoursAgo * 3_600_000).toISOString().replace('Z', '');
		const move = (id, game_id, hoursAgo) => ({
			...BODY.events[0],
			snapshot_id: id,
			game_id,
			at: at(hoursAgo)
		});
		const games = {
			7: { ...BODY.games[7] },
			8: { game_id: 8, title: 'Cascadia', image_url: null, series: [] }
		};

		it('draws the line above the first game already seen', async () => {
			api.getTimelineEvents.mockResolvedValue({
				events: [move(2, 7, 1), move(1, 8, 3)],
				games,
				next_cursor: null
			});
			api.getTimelineSeen.mockResolvedValue({ seen_at: at(2) });
			render(Timeline);
			const line = await screen.findByText(/Caught up — seen/);
			const cascadia = screen.getByText('Cascadia');
			const ark = screen.getByText('Ark Nova');
			expect(ark.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
			expect(
				line.compareDocumentPosition(cascadia) & Node.DOCUMENT_POSITION_FOLLOWING
			).toBeTruthy();
			expect(screen.getByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
		});

		it('marks up to the newest move loaded', async () => {
			const newest = move(2, 7, 1);
			api.getTimelineEvents.mockResolvedValue({ events: [newest], games, next_cursor: null });
			api.markTimelineSeen.mockResolvedValue({ seen_at: newest.at, stores: {} });
			render(Timeline);
			await fireEvent.click(await screen.findByRole('button', { name: /Mark 1 as seen/ }));
			expect(api.markTimelineSeen).toHaveBeenCalledWith(newest.at, []);
			expect(await screen.findByRole('button', { name: 'Caught up' })).toBeDisabled();
		});

		it('won’t mark caught up from a narrowed view', async () => {
			api.getTimelineEvents.mockResolvedValue({
				events: [move(2, 7, 1)],
				games,
				next_cursor: null
			});
			render(Timeline);
			await screen.findByText('Ark Nova');
			await fireEvent.click(screen.getByRole('button', { name: 'Drops' }));
			expect(screen.getByRole('button', { name: /Mark 1 as seen/ })).toBeDisabled();
			expect(screen.getByText(/Clear the kind, price and watchlist/)).toBeVisible();
		});

		it('treats a remembered choice of every kind as no filter', async () => {
			localStorage.setItem(
				'gd-timeline-filters',
				JSON.stringify({ kinds: ['rise', 'drop', 'listed', 'restock', 'oos'] })
			);
			render(Timeline);
			expect(await screen.findByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
			expect(lastParams().kinds).toBe('');
			expect(screen.queryByText(/Clear the kind/)).not.toBeInTheDocument();
		});

		it('treats choosing every kind by hand as no filter', async () => {
			render(Timeline);
			await screen.findByText('Ark Nova');
			for (const name of ['Drops', 'Rises', 'Restocks', 'Sold out', 'New']) {
				await fireEvent.click(screen.getByRole('button', { name }));
			}
			expect(lastParams().kinds).toBe('');
			expect(JSON.parse(localStorage.getItem('gd-timeline-filters') ?? '{}').kinds).toEqual([]);
			expect(await screen.findByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
		});

		it('forgets a remembered shop that no longer exists', async () => {
			localStorage.setItem('gd-timeline-filters', JSON.stringify({ stores: ['gone'] }));
			render(Timeline);
			expect(await screen.findByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
			expect(lastParams().stores).toBe('');
			expect(JSON.parse(localStorage.getItem('gd-timeline-filters') ?? '{}').stores).toEqual([]);
		});

		it('keeps a remembered shop that still exists', async () => {
			localStorage.setItem('gd-timeline-filters', JSON.stringify({ stores: ['gone', 'a'] }));
			render(Timeline);
			await screen.findByText('Ark Nova');
			expect(lastParams().stores).toBe('a');
		});

		it('keeps remembered shops until the shop names arrive', async () => {
			storeColors.names = new Map();
			localStorage.setItem('gd-timeline-filters', JSON.stringify({ stores: ['a', 'gone'] }));
			render(Timeline);
			await screen.findByText('Ark Nova');
			expect(lastParams().stores).toBe('a,gone');
			storeColors.names = new Map([['a', 'Shop A']]);
			await waitFor(() => expect(lastParams().stores).toBe('a'));
		});

		describe('shop by shop', () => {
			const inShop = (id, store_id, hoursAgo) => ({ ...move(id, 7, hoursAgo), store_id });

			it('marks only the chosen shops', async () => {
				const newest = inShop(2, 'b', 1);
				api.getTimelineEvents.mockResolvedValue({ events: [newest], games, next_cursor: null });
				api.markTimelineSeen.mockResolvedValue({ seen_at: null, stores: { b: newest.at } });
				render(Timeline);
				await screen.findByText('Ark Nova');
				await fireEvent.click(screen.getByRole('button', { name: 'Shop B' }));
				await fireEvent.click(await screen.findByRole('button', { name: /Mark 1 as seen/ }));
				expect(api.markTimelineSeen).toHaveBeenCalledWith(newest.at, ['b']);
				expect(await screen.findByRole('button', { name: 'Caught up' })).toBeDisabled();
			});

			it('still won’t mark a shop through a kind filter', async () => {
				api.getTimelineEvents.mockResolvedValue({
					events: [inShop(2, 'b', 1)],
					games,
					next_cursor: null
				});
				render(Timeline);
				await screen.findByText('Ark Nova');
				await fireEvent.click(screen.getByRole('button', { name: 'Shop B' }));
				await fireEvent.click(screen.getByRole('button', { name: 'Drops' }));
				expect(screen.getByRole('button', { name: /Mark 1 as seen/ })).toBeDisabled();
			});

			it('counts and dims a marked shop while another stays unseen', async () => {
				api.getTimelineEvents.mockResolvedValue({
					events: [inShop(3, 'a', 1), { ...move(2, 8, 2), store_id: 'b' }],
					games,
					next_cursor: null
				});
				api.getTimelineSeen.mockResolvedValue({ seen_at: null, stores: { a: at(0.5) } });
				render(Timeline);
				expect(await screen.findByRole('button', { name: /Mark 1 as seen/ })).toBeEnabled();
				expect(screen.getByText('Ark Nova').closest('article')).toHaveClass('opacity-60');
				expect(screen.getByText('Cascadia').closest('article')).not.toHaveClass('opacity-60');
			});

			it('draws the line only below the last unseen move', async () => {
				api.getTimelineEvents.mockResolvedValue({
					events: [
						inShop(4, 'a', 1),
						{ ...move(3, 8, 2), store_id: 'b' },
						{ ...move(2, 9, 3), store_id: 'a' }
					],
					games: { ...games, 9: { game_id: 9, title: 'Wingspan', image_url: null, series: [] } },
					next_cursor: null
				});
				api.getTimelineSeen.mockResolvedValue({ seen_at: null, stores: { a: at(0.5) } });
				render(Timeline);
				const line = await screen.findByText(/Caught up — seen/);
				const before = screen.getByText('Cascadia');
				const after = screen.getByText('Wingspan');
				expect(
					before.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING
				).toBeTruthy();
				expect(line.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
			});

			it('won’t claim caught up while later pages may hold another shop’s moves', async () => {
				api.getTimelineEvents.mockResolvedValue({
					events: [inShop(2, 'a', 1)],
					games,
					next_cursor: 'c1'
				});
				api.getTimelineSeen.mockResolvedValue({ seen_at: null, stores: { a: at(0.5) } });
				render(Timeline);
				expect(await screen.findByRole('button', { name: 'Nothing new so far' })).toBeDisabled();
				expect(screen.queryByText(/Caught up — seen/)).not.toBeInTheDocument();
			});

			it('claims caught up with more pages once the global line covers them', async () => {
				api.getTimelineEvents.mockResolvedValue({
					events: [inShop(2, 'a', 1)],
					games,
					next_cursor: 'c1'
				});
				api.getTimelineSeen.mockResolvedValue({ seen_at: at(0.5), stores: { a: at(0.6) } });
				render(Timeline);
				expect(await screen.findByRole('button', { name: 'Caught up' })).toBeDisabled();
				expect(screen.getByText(/Caught up — seen/)).toBeInTheDocument();
			});
		});
	});
});
