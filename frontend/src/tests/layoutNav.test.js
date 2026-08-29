import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';

vi.mock('$lib/api.js', () => ({}));
vi.mock('$lib/watchlist.svelte.js', () => ({
	watchlist: { load: vi.fn(), has: () => false, toggle: vi.fn(), ids: [] }
}));
vi.mock('$lib/hidden.svelte.js', () => ({
	hidden: { load: vi.fn(), has: () => false, toggle: vi.fn(), ids: [] }
}));
vi.mock('$lib/notifications.svelte.js', () => ({
	notifications: { load: vi.fn(), items: [], unread: 0, markAllRead: vi.fn() }
}));
vi.mock('$lib/storeColors.svelte.js', () => ({
	storeColors: { load: vi.fn(), get: () => null }
}));

import Layout from '../routes/+layout.svelte';

const children = createRawSnippet(() => ({ render: () => '<main></main>' }));
const renderLayout = () => render(Layout, { props: { children } });

const openMore = async () => {
	await fireEvent.click(screen.getByRole('button', { name: 'More' }));
};

describe('primary navigation', () => {
	it('offers the changes feed alongside the other feeds', () => {
		renderLayout();
		const links = screen.getAllByRole('link', { name: /changes/i });
		expect(links.some((l) => l.getAttribute('href') === '/changes')).toBe(true);
	});
});

describe('layout overflow menu', () => {
	it('links to the source repository in a new tab', async () => {
		renderLayout();
		await openMore();

		const link = screen.getByRole('link', { name: /github/i });
		expect(link).toHaveAttribute('href', 'https://github.com/Dr-Blank/gamedrop');
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', 'noreferrer');
	});

	it('leaves internal menu links in the same tab', async () => {
		renderLayout();
		await openMore();

		const link = screen.getByRole('link', { name: /settings/i });
		expect(link).toHaveAttribute('href', '/settings');
		expect(link).not.toHaveAttribute('target');
	});
});
