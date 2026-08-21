import { describe, it, expect } from 'vitest';
import { inr } from '$lib/priceFormat.svelte.js';

describe('inr', () => {
	it('formats and handles missing prices', () => {
		expect(inr(1234)).toBe('₹1,234');
		expect(inr(null)).toBe('—');
	});
});
