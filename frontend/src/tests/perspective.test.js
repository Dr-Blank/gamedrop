import { describe, it, expect } from 'vitest';
import { inferFocusStore } from '$lib/perspective.js';

const group = (...conditions) => ({ type: 'group', op: 'and', conditions });

describe('inferFocusStore', () => {
	it('names no shop for a query that names none', () => {
		expect(inferFocusStore(null)).toBeNull();
		expect(
			inferFocusStore(group({ type: 'condition', field: 'price', op: 'lt', value: 10 }))
		).toBeNull();
	});

	it('follows a filter on one shop', () => {
		expect(
			inferFocusStore(group({ type: 'condition', field: 'store_id', op: 'eq', value: 'shop-a' }))
		).toBe('shop-a');
	});

	it('takes the side a store comparison is written from', () => {
		expect(
			inferFocusStore(
				group({ type: 'store_compare', store_a: 'shop-a', store_b: 'shop-b', op: 'lt' })
			)
		).toBe('shop-a');
	});

	it("follows a sync run's own window, which names its shop", () => {
		expect(
			inferFocusStore(group({ type: 'change_window', since: '-1d', store_id: 'shop-b' }))
		).toBe('shop-b');
	});

	it('finds a shop named inside a nested group', () => {
		expect(
			inferFocusStore(
				group(group({ type: 'condition', field: 'store_id', op: 'eq', value: 'shop-c' }))
			)
		).toBe('shop-c');
	});

	it('falls back to the shop a gap sort measures from', () => {
		expect(inferFocusStore(null, [{ type: 'store_gap', store_a: 'shop-d', store_b: '*' }])).toBe(
			'shop-d'
		);
	});

	it('never quotes a shop the query excludes', () => {
		const excluded = {
			type: 'group',
			op: 'not',
			conditions: [{ type: 'condition', field: 'store_id', op: 'eq', value: 'shop-a' }]
		};
		expect(inferFocusStore(group(excluded))).toBeNull();
	});

	it('treats a wildcard rival as naming no shop', () => {
		expect(
			inferFocusStore(group({ type: 'store_compare', store_a: '*', store_b: 'shop-b', op: 'lt' }))
		).toBeNull();
		expect(inferFocusStore(null, [{ type: 'store_gap', store_a: 'shop-a' }])).toBe('shop-a');
	});

	it('ignores a store filter that has not been given a shop yet', () => {
		expect(
			inferFocusStore(group({ type: 'condition', field: 'store_id', op: 'eq', value: '' }))
		).toBeNull();
	});
});
