import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import InfiniteScroll from '$lib/components/InfiniteScroll.svelte';

/** Captured observer instances so a test can fire an intersection by hand. */
let observers = [];

class FakeIntersectionObserver {
	constructor(cb) {
		this.cb = cb;
		this.targets = new Set();
		observers.push(this);
	}
	observe(el) {
		this.targets.add(el);
	}
	unobserve(el) {
		this.targets.delete(el);
	}
	disconnect() {
		this.targets.clear();
	}
	trigger(isIntersecting = true) {
		this.cb([{ isIntersecting, target: [...this.targets][0] }]);
	}
}

describe('InfiniteScroll', () => {
	beforeEach(() => {
		observers = [];
		vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
	});

	it('observes the sentinel and hides the manual button', async () => {
		render(InfiniteScroll, { hasMore: true, loading: false, onload: vi.fn() });
		await waitFor(() => expect(observers).toHaveLength(1));
		expect(observers[0].targets.size).toBe(1);
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('loads the next page when the sentinel scrolls into view', async () => {
		const onload = vi.fn();
		render(InfiniteScroll, { hasMore: true, loading: false, onload });
		await waitFor(() => expect(observers).toHaveLength(1));

		observers[0].trigger();
		await waitFor(() => expect(onload).toHaveBeenCalledTimes(1));
	});

	it('does not fire again while a load is in flight', async () => {
		let resolve;
		const onload = vi.fn(() => new Promise((r) => (resolve = r)));
		render(InfiniteScroll, { hasMore: true, loading: false, onload });
		await waitFor(() => expect(observers).toHaveLength(1));

		observers[0].trigger();
		observers[0].trigger();
		expect(onload).toHaveBeenCalledTimes(1);
		resolve();
	});

	it('renders nothing once the list is exhausted', () => {
		const { container } = render(InfiniteScroll, {
			hasMore: false,
			loading: false,
			onload: vi.fn()
		});
		expect(container.textContent.trim()).toBe('');
	});

	it('falls back to a button without IntersectionObserver', async () => {
		vi.stubGlobal('IntersectionObserver', undefined);
		const onload = vi.fn();
		render(InfiniteScroll, { hasMore: true, loading: false, onload });
		const button = await screen.findByRole('button', { name: /load more/i });
		button.click();
		await waitFor(() => expect(onload).toHaveBeenCalled());
	});
});
