import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ProductCard from '$lib/components/ProductCard.svelte';

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
	const history = [{ price: 610 }, { price: 900 }, { price: 800 }];

	it('keeps the struck-through MRP out of the price line', () => {
		render(ProductCard, { props: { item, variant: 'browse', history } });
		expect(screen.queryByText('₹2,000')).not.toBeInTheDocument();
		expect(screen.getByText(/off MRP/)).toBeInTheDocument();
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
