import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({ inspectJsonApi: vi.fn() }));

import JsonApiMapping from '$lib/components/JsonApiMapping.svelte';
import * as api from '$lib/api.js';

const BASE = 'https://shop.test';
const config = {
	endpoint: '/v1/items',
	items_path: 'data',
	total_path: '',
	paging: 'none',
	page_param: '',
	size_param: '',
	page_size: 100,
	first_page: 1,
	collection_param: '',
	price_divisor: 1,
	fields: { id: 'id', title: 'name', price: 'price' }
};

describe('JsonApiMapping', () => {
	beforeEach(() => vi.clearAllMocks());

	it('explains where to find the API when none is known', () => {
		render(JsonApiMapping, { props: { baseUrl: BASE } });
		expect(screen.getByText(/DevTools → Network/)).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Find API/ })).toBeInTheDocument();
	});

	it('reads fields from a pasted API URL', async () => {
		api.inspectJsonApi.mockResolvedValue({
			config,
			total: null,
			warnings: ['2 of 10 items have no usable id or price.'],
			samples: [{ title: 'Azul', url: null, price: 2999, available: false, preorder: false }]
		});
		render(JsonApiMapping, { props: { baseUrl: BASE, collectionPath: '/c/x' } });

		await fireEvent.input(screen.getByLabelText('Product API URL'), {
			target: { value: `${BASE}/v1/items` }
		});
		await fireEvent.click(screen.getByRole('button', { name: /Read fields/ }));

		expect(api.inspectJsonApi).toHaveBeenCalledWith({
			base_url: BASE,
			collection_path: '/c/x',
			api_url: `${BASE}/v1/items`
		});
		expect(await screen.findByText('Azul')).toBeInTheDocument();
		expect(screen.getByText('Out of stock')).toBeInTheDocument();
		expect(screen.getByText(/2 of 10 items/)).toBeInTheDocument();
	});

	it('tests the mapping as edited', async () => {
		api.inspectJsonApi.mockResolvedValue({ config, total: 0, warnings: [], samples: [] });
		render(JsonApiMapping, { props: { baseUrl: BASE, config: structuredClone(config) } });

		await fireEvent.input(screen.getByDisplayValue('data'), { target: { value: 'items' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Test mapping' }));

		const sent = api.inspectJsonApi.mock.calls[0][0];
		expect(sent.config.items_path).toBe('items');
		expect(sent.api_url).toBeUndefined();
	});
});
