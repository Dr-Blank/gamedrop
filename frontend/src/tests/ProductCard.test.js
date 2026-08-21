import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ProductCard from '$lib/components/ProductCard.svelte';
import { priceFormat } from '$lib/priceFormat.svelte.js';

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

describe('ProductCard', () => {
	it('renders title and price', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByText('Catan')).toBeInTheDocument();
		expect(screen.getByText(/610/)).toBeInTheDocument();
	});

	it('shows "Add to watchlist" when not watched', () => {
		// Real store, empty map -> not watched.
		render(ProductCard, { props: { item } });
		expect(screen.getByLabelText('Add to watchlist')).toBeInTheDocument();
	});

	it('leaves removal to the heart — no trash button, no Details', () => {
		render(ProductCard, { props: { item } });
		expect(screen.queryByTitle('Remove from watchlist')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument();
	});

	it('tints the store button with the shop colour', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByRole('link', { name: 'Store' }).getAttribute('style')).toContain(
			'border-color'
		);
	});
});

describe('ProductCard target chip', () => {
	it('offers a target on any watched card', () => {
		render(ProductCard, { props: { item } });
		expect(screen.getByTitle('Set target price')).toBeInTheDocument();
		expect(screen.getByText('any drop')).toBeInTheDocument();
	});

	it('quotes the target once one is set', () => {
		const withTarget = { ...item, watchlist: { id: 1, target_price: 450 } };
		render(ProductCard, { props: { item: withTarget } });
		expect(screen.getByText('₹450')).toBeInTheDocument();
	});

	it('stays off cards for games that are not watched', () => {
		const unwatched = { ...item, watchlist: null };
		render(ProductCard, { props: { item: unwatched } });
		expect(screen.queryByTitle('Set target price')).not.toBeInTheDocument();
	});
});

describe('ProductCard price rounding', () => {
	const charm = { ...item, latest_price: { price: 1999, available: true } };

	beforeEach(() => {
		priceFormat.mode = 'nearest-10';
	});

	it('rounds a charm price off by default', () => {
		render(ProductCard, { props: { item: charm } });
		expect(screen.getByText('₹2,000')).toBeInTheDocument();
	});

	it('quotes it exactly once rounding is off', () => {
		priceFormat.mode = 'off';
		render(ProductCard, { props: { item: charm } });
		expect(screen.getByText('₹1,999')).toBeInTheDocument();
	});

	it('rounds both sides before subtracting, so the gap matches the prices shown', () => {
		const twoShops = {
			...charm,
			latest_price: { price: 990, available: true },
			compare: {
				listing_count: 2,
				store_ids: ['satyam', 'other'],
				cheapest: { product_id: 2, store_id: 'satyam', price: 990, available: true },
				cheapest_in_stock: { product_id: 2, store_id: 'satyam', price: 990, available: true },
				offers: [
					{ product_id: 2, store_id: 'satyam', price: 990, available: true },
					{ product_id: 3, store_id: 'other', price: 999, available: true }
				]
			}
		};
		render(ProductCard, { props: { item: twoShops } });
		expect(screen.getByText('₹10 less than other')).toBeInTheDocument();
		expect(screen.queryByText('₹9 less than other')).not.toBeInTheDocument();
	});

	it('rounds the target chip too', () => {
		const withTarget = { ...charm, watchlist: { id: 1, target_price: 1499 } };
		render(ProductCard, { props: { item: withTarget } });
		expect(screen.getByText('₹1,500')).toBeInTheDocument();
	});
});

describe('ProductCard tab/new-window support', () => {
	it('wraps card in <a> with correct href (enables browser middle-click and right-click new tab)', () => {
		const { container } = render(ProductCard, { props: { item } });
		const anchor = container.querySelector('a[href="/games/5?store=satyam"]');
		expect(anchor).toBeInTheDocument();
	});

	it('clicking the target chip prevents card anchor from navigating', async () => {
		vi.stubGlobal(
			'prompt',
			vi.fn(() => null)
		);
		const { container } = render(ProductCard, { props: { item } });
		let anchorEvent;
		container.querySelector('a[href="/games/5?store=satyam"]').addEventListener('click', (e) => {
			anchorEvent = e;
		});
		await fireEvent.click(screen.getByTitle('Set target price'));
		expect(anchorEvent?.defaultPrevented).toBe(true);
	});

	it('clicking hide button prevents card anchor from navigating', async () => {
		const { container } = render(ProductCard, { props: { item } });
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
		render(ProductCard, { props: { item: { ...item, price_history: history } } });
		expect(screen.queryByText('₹2,000')).not.toBeInTheDocument();
		expect(screen.queryByText(/off MRP/)).not.toBeInTheDocument();
		expect(screen.getByText('changed 3 days ago')).toBeInTheDocument();
	});

	it('leaves the price age off a card whose history has no timestamps', () => {
		render(ProductCard, {
			props: { item: { ...item, price_history: [{ price: 610 }, { price: 900 }] } }
		});
		expect(screen.queryByText(/changed|same for/)).not.toBeInTheDocument();
	});

	it('draws the trend for a one-shop card straight off the item', () => {
		// Regression: the card used to read a `history` prop that only the browse
		// grid passed, so search and the home shelves drew no line at all.
		const { container } = render(ProductCard, {
			props: { item: { ...item, price_history: history } }
		});
		expect(container.querySelector('svg polyline')).toBeInTheDocument();
	});

	it('draws nothing when the listing has no readings', () => {
		const { container } = render(ProductCard, { props: { item } });
		expect(container.querySelector('svg polyline')).toBeNull();
	});

	it('says how far the price sits above its own low', () => {
		render(ProductCard, { props: { item: { ...item, price_history: history } } });
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
		render(ProductCard, { props: { item: multi } });
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
		const { container } = render(ProductCard, { props: { item: twice } });
		expect(container.querySelectorAll('span[title="satyam"]')).toHaveLength(1);
		expect(container.querySelectorAll('span[title="other"]')).toHaveLength(1);
	});
});

describe('ProductCard BGG link', () => {
	it('opens a search and takes the pasted link when the game has no BGG id', async () => {
		const open = vi.fn();
		vi.stubGlobal('open', open);
		const onlinked = vi.fn();
		render(ProductCard, { props: { item, onlinked } });

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
		render(ProductCard, { props: { item: linked } });
		expect(screen.getByLabelText('Open on BoardGameGeek')).toHaveAttribute(
			'href',
			'https://boardgamegeek.com/boardgame/42'
		);
		expect(screen.queryByLabelText('Paste BGG link')).not.toBeInTheDocument();
	});
});
