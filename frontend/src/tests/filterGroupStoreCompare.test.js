import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

import Harness from './fixtures/FilterHarness.svelte';

const STORES = [
	{ id: 'shop-a', name: 'Shop A' },
	{ id: 'shop-b', name: 'Shop B' },
	{ id: 'shop-c', name: 'Shop C' }
];

function renderGroup(conditions = []) {
	let state;
	render(Harness, {
		props: {
			fields: [{ name: 'price', label: 'Price', type: 'float', ops: ['lt'] }],
			stores: STORES,
			initial: { type: 'group', op: 'and', conditions },
			onstate: (g) => (state = g)
		}
	});
	return () => state;
}

const compare = (over = {}) => [
	{
		type: 'store_compare',
		store_a: 'shop-a',
		store_b: 'shop-b',
		op: 'lt',
		value: 0,
		mode: 'abs',
		stock: 'in_stock',
		...over
	}
];

describe('store comparison filter', () => {
	it('opens on buyable offers only, so the gap is one you can act on', async () => {
		const state = renderGroup();
		await fireEvent.click(screen.getByRole('button', { name: /compare stores/i }));
		expect(state().conditions[0]).toMatchObject({ type: 'store_compare', stock: 'in_stock' });
	});

	it('offers every other shop at once as the rival', () => {
		renderGroup(compare());
		const rivals = [...screen.getByLabelText('Rival store').options].map((o) => o.value);
		expect(rivals).toEqual(['*', 'shop-b', 'shop-c']);
	});

	it('can count out-of-stock offers when asked', async () => {
		const state = renderGroup(compare());
		await fireEvent.change(screen.getByLabelText('Gap stock scope'), {
			target: { value: 'any' }
		});
		expect(state().conditions[0].stock).toBe('any');
	});

	it('keeps a wildcard rival out of the shop list', () => {
		renderGroup(compare({ store_b: '*' }));
		expect(screen.getByLabelText('Rival store')).toHaveValue('*');
	});

	it('drops a rival that the compared shop has just become', async () => {
		const state = renderGroup(compare({ store_a: 'shop-a', store_b: 'shop-b' }));
		await fireEvent.change(screen.getByLabelText('Compared store'), {
			target: { value: 'shop-b' }
		});
		expect(state().conditions[0].store_b).toBe('*');
	});

	it('shows the default scope for a condition saved before it existed', () => {
		renderGroup(compare({ stock: undefined }));
		expect(screen.getByLabelText('Gap stock scope')).toHaveValue('in_stock');
	});
});
