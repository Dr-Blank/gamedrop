import { describe, it, expect, vi, beforeEach } from 'vitest';
import { defaultColor, tint, DEFAULT_PALETTE, storeColors } from '$lib/storeColors.svelte.js';
import * as api from '$lib/api.js';

vi.mock('$lib/api.js', () => ({ getStores: vi.fn() }));

describe('store colours', () => {
	beforeEach(() => {
		storeColors.saved = new Map();
		storeColors.names = new Map();
	});

	it('derives the same colour for a store id every time', () => {
		expect(defaultColor('shopify-a')).toBe(defaultColor('shopify-a'));
		expect(DEFAULT_PALETTE).toContain(defaultColor('shopify-a'));
	});

	it('gives different stores different colours', () => {
		const picked = new Set(['alpha', 'beta', 'gamma', 'delta'].map(defaultColor));
		expect(picked.size).toBeGreaterThan(1);
	});

	it('prefers a saved colour over the derived one', async () => {
		api.getStores.mockResolvedValue([{ id: 'a', name: 'A', color: '#123456' }]);
		await storeColors.load();
		expect(storeColors.of('a')).toBe('#123456');
	});

	it('falls back to the derived colour when none is saved', async () => {
		api.getStores.mockResolvedValue([{ id: 'a', name: 'A', color: null }]);
		await storeColors.load();
		expect(storeColors.of('a')).toBe(defaultColor('a'));
	});

	it('set(null) drops back to the derived colour', () => {
		storeColors.set('a', '#123456');
		expect(storeColors.of('a')).toBe('#123456');
		storeColors.set('a', null);
		expect(storeColors.of('a')).toBe(defaultColor('a'));
	});

	it('tint converts hex to rgba', () => {
		expect(tint('#10b981', 0.25)).toBe('rgba(16,185,129,0.25)');
	});

	it('tint survives a missing colour', () => {
		expect(tint(undefined, 0.5)).toBe('rgba(120,120,120,0.5)');
	});
});
