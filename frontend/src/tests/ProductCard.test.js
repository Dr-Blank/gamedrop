import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ProductCard from '$lib/components/ProductCard.svelte';

const linkBgg = vi.fn(async () => ({}));
vi.mock('$lib/api.js', async (original) => ({
	...(await original()),
	linkBgg: (...a) => linkBgg(...a)
}));

const item = {
	product: {
		id: 2,
		game_id: 5,
		title: 'Catan',
		store_id: 'satyam',
		url: 'https://x/p',
		image_url: null
	},
	game: { id: 5, title: 'Catan', hidden: false, bgg_id: null, note: null },
	latest_price: { price: 610, available: true, compare_at_price: 2000 },
	bgg: null,
	override: null,
	discount_pct: 69.5,
	watchlist: { id: 1, target_price: null }
};

describe('ProductCard (watchlist variant)', () => {
	it('renders title and price', () => {
		render(ProductCard, { props: { item, variant: 'watchlist' } });
		expect(screen.getByText('Catan')).toBeInTheDocument();
		expect(screen.getByText(/610/)).toBeInTheDocument();
	});

	it('fires onremove when the remove button is clicked', async () => {
		const onremove = vi.fn();
		render(ProductCard, { props: { item, variant: 'watchlist', onremove } });
		await fireEvent.click(screen.getByTitle('Remove from watchlist'));
		expect(onremove).toHaveBeenCalledOnce();
	});

	it('shows "any drop" when no target price set', () => {
		render(ProductCard, { props: { item, variant: 'watchlist', target: null } });
		expect(screen.getByText('any drop')).toBeInTheDocument();
	});

	it('browse variant shows "Add to watchlist" when not watched', () => {
		// Real store, empty map -> not watched.
		render(ProductCard, { props: { item, variant: 'browse' } });
		expect(screen.getByLabelText('Add to watchlist')).toBeInTheDocument();
	});
});

describe('ProductCard tab/new-window support', () => {
	it('wraps card in <a> with correct href (enables browser middle-click and right-click new tab)', () => {
		const { container } = render(ProductCard, { props: { item, variant: 'browse' } });
		const anchor = container.querySelector('a[href="/games/5?store=satyam"]');
		expect(anchor).toBeInTheDocument();
	});

	it('watchlist variant also has correct href anchor', () => {
		const { container } = render(ProductCard, { props: { item, variant: 'watchlist' } });
		const anchor = container.querySelector('a[href="/games/5?store=satyam"]');
		expect(anchor).toBeInTheDocument();
	});

	it('hidden variant also has correct href anchor', () => {
		const { container } = render(ProductCard, {
			props: { item: { ...item, bgg: null }, variant: 'hidden' }
		});
		const anchor = container.querySelector('a[href="/games/5?store=satyam"]');
		expect(anchor).toBeInTheDocument();
	});

	it('clicking remove button prevents card anchor from navigating', async () => {
		const onremove = vi.fn();
		const { container } = render(ProductCard, { props: { item, variant: 'watchlist', onremove } });
		let anchorEvent;
		container.querySelector('a[href="/games/5?store=satyam"]').addEventListener('click', (e) => {
			anchorEvent = e;
		});
		await fireEvent.click(screen.getByTitle('Remove from watchlist'));
		expect(onremove).toHaveBeenCalledOnce();
		expect(anchorEvent?.defaultPrevented).toBe(true);
	});

	it('clicking hide button prevents card anchor from navigating', async () => {
		const { container } = render(ProductCard, { props: { item, variant: 'browse' } });
		let anchorEvent;
		container.querySelector('a[href="/games/5?store=satyam"]').addEventListener('click', (e) => {
			anchorEvent = e;
		});
		await fireEvent.click(screen.getByTitle('Hide this game permanently'));
		expect(anchorEvent?.defaultPrevented).toBe(true);
	});
});

describe('ProductCard price line', () => {
	const day = (n) => new Date(Date.now() - n * 86400000).toISOString();
	const history = [
		{ price: 610, recorded_at: day(0) },
		{ price: 610, recorded_at: day(3) },
		{ price: 900, recorded_at: day(9) },
		{ price: 800, recorded_at: day(12) }
	];

	it('says how long the price has stood instead of quoting an MRP', () => {
		render(ProductCard, { props: { item, variant: 'browse', history } });
		expect(screen.queryByText('₹2,000')).not.toBeInTheDocument();
		expect(screen.queryByText(/off MRP/)).not.toBeInTheDocument();
		expect(screen.getByText('changed 3 days ago')).toBeInTheDocument();
	});

	it('leaves the price age off a card whose history has no timestamps', () => {
		render(ProductCard, {
			props: { item, variant: 'browse', history: [{ price: 610 }, { price: 900 }] }
		});
		expect(screen.queryByText(/changed|same for/)).not.toBeInTheDocument();
	});

	it('says how far the price sits above its own low', () => {
		render(ProductCard, { props: { item, variant: 'browse', history } });
		expect(screen.getByText('cheapest it has been')).toBeInTheDocument();
	});

	it('quotes the saving against the dearest shop when several sell it', () => {
		const multi = {
			...item,
			compare: {
				listing_count: 2,
				store_ids: ['satyam', 'other'],
				cheapest: { product_id: 2, store_id: 'satyam', price: 610, available: true },
				cheapest_in_stock: { product_id: 2, store_id: 'satyam', price: 610, available: true },
				offers: [
					{ product_id: 2, store_id: 'satyam', price: 610, available: true },
					{ product_id: 3, store_id: 'other', price: 990, available: true }
				]
			}
		};
		render(ProductCard, { props: { item: multi, variant: 'browse' } });
		expect(screen.getByText('₹380 less than other')).toBeInTheDocument();
	});

	it('gives a shop one dot even when it lists the game twice', () => {
		const twice = {
			...item,
			compare: {
				listing_count: 3,
				store_ids: ['satyam', 'other'],
				cheapest: { product_id: 2, store_id: 'satyam', price: 610, available: true },
				cheapest_in_stock: { product_id: 2, store_id: 'satyam', price: 610, available: true },
				offers: [
					{ product_id: 2, store_id: 'satyam', price: 610, available: true },
					{ product_id: 4, store_id: 'satyam', price: 700, available: true },
					{ product_id: 3, store_id: 'other', price: 990, available: true }
				]
			}
		};
		const { container } = render(ProductCard, { props: { item: twice, variant: 'browse' } });
		expect(container.querySelectorAll('span[title="satyam"]')).toHaveLength(1);
		expect(container.querySelectorAll('span[title="other"]')).toHaveLength(1);
	});
});

describe('ProductCard BGG link', () => {
	it('opens a search and takes the pasted link when the game has no BGG id', async () => {
		const open = vi.fn();
		vi.stubGlobal('open', open);
		const onlinked = vi.fn();
		render(ProductCard, { props: { item, variant: 'browse', onlinked } });

		await fireEvent.click(screen.getByLabelText('Find on BoardGameGeek'));
		expect(open).toHaveBeenCalledWith(expect.stringContaining('BGG%20Catan'), '_blank', 'noopener');

		const field = screen.getByLabelText('Paste BGG link');
		await fireEvent.input(field, {
			target: { value: 'https://boardgamegeek.com/boardgame/13/catan' }
		});
		expect(linkBgg).toHaveBeenCalledWith(13, 2);
		expect(await screen.findByLabelText('Open on BoardGameGeek')).toHaveAttribute(
			'href',
			'https://boardgamegeek.com/boardgame/13'
		);
		expect(onlinked).toHaveBeenCalledWith(13);
	});

	it('links straight out when the game is already on BGG', () => {
		const linked = { ...item, game: { ...item.game, bgg_id: 42 } };
		render(ProductCard, { props: { item: linked, variant: 'browse' } });
		expect(screen.getByLabelText('Open on BoardGameGeek')).toHaveAttribute(
			'href',
			'https://boardgamegeek.com/boardgame/42'
		);
		expect(screen.queryByLabelText('Paste BGG link')).not.toBeInTheDocument();
	});
});
