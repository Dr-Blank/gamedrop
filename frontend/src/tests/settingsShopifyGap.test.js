import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import Settings from '../routes/settings/+page.svelte';

describe('Shopify pacing setting', () => {
	let saved;
	let refuse;

	beforeEach(() => {
		saved = 2;
		refuse = false;
		vi.stubGlobal(
			'IntersectionObserver',
			class {
				observe() {}
				unobserve() {}
				disconnect() {}
			}
		);
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url, init) => {
				if (init?.method === 'PUT' && !refuse) {
					saved = JSON.parse(init.body).shopify_request_gap_sec;
				}
				return {
					ok: !refuse,
					json: async () => ({ ntfy_server: '', shopify_request_gap_sec: saved })
				};
			})
		);
	});

	afterEach(() => vi.unstubAllGlobals());

	const field = () => screen.findByLabelText(/Seconds between requests/);

	it('shows the saved gap and saves a change', async () => {
		render(Settings);
		const input = await field();
		await waitFor(() => expect(input).toHaveValue(2));
		await fireEvent.input(input, { target: { value: '5' } });
		await fireEvent.change(input);
		await waitFor(() => expect(saved).toBe(5));
		expect(input).toHaveValue(5);
	});

	it('snaps back when the server refuses the value', async () => {
		render(Settings);
		const input = await field();
		await waitFor(() => expect(input).toHaveValue(2));
		refuse = true;
		await fireEvent.input(input, { target: { value: '99' } });
		await fireEvent.change(input);
		await waitFor(() => expect(input).toHaveValue(2));
	});
});
