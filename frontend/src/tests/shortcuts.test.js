import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const goto = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...a) => goto(...a) }));

const toggleTheme = vi.fn();
vi.mock('$lib/theme.svelte.js', () => ({ theme: { toggle: () => toggleTheme() } }));

import { tick } from 'svelte';
import { render } from '@testing-library/svelte';
import { shortcuts, BROWSE_SHORTCUTS, keyLabels } from '$lib/shortcuts.svelte.js';
import RegisterHarness from './fixtures/RegisterHarness.svelte';

/** @param {string} key @param {object} opts */
function press(key, { target = document.body, ...mods } = {}) {
	const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...mods });
	Object.defineProperty(e, 'target', { value: target });
	shortcuts.handle(e);
	return e;
}

describe('keyboard shortcuts', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		shortcuts.helpOpen = false;
		shortcuts.pageShortcuts = [];
	});

	afterEach(() => {
		press('Escape');
	});

	it('runs a chord only after the full sequence', () => {
		press('g');
		expect(goto).not.toHaveBeenCalled();
		expect(shortcuts.pending).toBe('g');

		press('w');
		expect(goto).toHaveBeenCalledWith('/watchlist');
		expect(shortcuts.pending).toBe('');
	});

	it('g c goes to the changes feed', () => {
		press('g');
		press('c');
		expect(goto).toHaveBeenCalledWith('/changes');
	});

	it('abandons a chord on an unknown second key', () => {
		press('g');
		press('q');
		expect(goto).not.toHaveBeenCalled();
		expect(shortcuts.pending).toBe('');
	});

	it('focuses search from / and from the modifier combos', () => {
		const focus = vi.fn();
		const cleanup = shortcuts.registerSearchFocus(focus);

		press('/');
		press('k', { ctrlKey: true });
		press('f', { metaKey: true });
		expect(focus).toHaveBeenCalledTimes(3);
		cleanup();
	});

	it('ignores plain keys while typing but still honours combos', () => {
		const focus = vi.fn();
		const cleanup = shortcuts.registerSearchFocus(focus);
		const input = document.createElement('input');

		press('t', { target: input });
		expect(toggleTheme).not.toHaveBeenCalled();

		press('f', { target: input, ctrlKey: true });
		expect(focus).toHaveBeenCalledTimes(1);
		cleanup();
	});

	it('opens the help sheet from ? and from ctrl+/', () => {
		press('?', { shiftKey: true });
		expect(shortcuts.helpOpen).toBe(true);

		press('Escape');
		press('/', { ctrlKey: true });
		expect(shortcuts.helpOpen).toBe(true);
	});

	it('escape closes the help sheet and leaves the field', () => {
		shortcuts.helpOpen = true;
		const input = document.createElement('input');
		input.blur = vi.fn();

		press('Escape', { target: input });
		expect(shortcuts.helpOpen).toBe(false);
		expect(input.blur).toHaveBeenCalled();
	});

	it('does not navigate behind an open help sheet', () => {
		shortcuts.helpOpen = true;
		press('g');
		press('h');
		expect(goto).not.toHaveBeenCalled();
	});

	it('binds page shortcuts to page handlers and drops them on cleanup', () => {
		const toggleFilters = vi.fn();
		const cleanup = shortcuts.register(BROWSE_SHORTCUTS, { f: toggleFilters });

		press('f');
		expect(toggleFilters).toHaveBeenCalledTimes(1);

		cleanup();
		press('f');
		expect(toggleFilters).toHaveBeenCalledTimes(1);
	});

	it('prevents default only for keys it consumes', () => {
		expect(press('t').defaultPrevented).toBe(true);
		expect(press('q').defaultPrevented).toBe(false);
	});

	it('leaves Enter to the browser so a focused card still opens', () => {
		expect(press('Enter').defaultPrevented).toBe(false);
	});

	it('moves the card cursor with j and k', () => {
		document.body.innerHTML = `
			<a href="#a" data-product-card id="a"><button data-action="watch"></button></a>
			<a href="#b" data-product-card id="b"><button data-action="watch"></button></a>`;
		for (const el of document.querySelectorAll('a')) el.scrollIntoView = vi.fn();

		press('j');
		expect(document.activeElement.id).toBe('a');
		press('j');
		expect(document.activeElement.id).toBe('b');
		press('k');
		expect(document.activeElement.id).toBe('a');

		document.body.innerHTML = '';
	});

	it('w clicks the watch button of the focused card only', () => {
		document.body.innerHTML = `
			<a href="#a" data-product-card id="a"><button data-action="watch"></button></a>
			<a href="#b" data-product-card id="b"><button data-action="watch"></button></a>`;
		const [first, second] = document.querySelectorAll('[data-action="watch"]');
		first.onclick = vi.fn();
		second.onclick = vi.fn();
		for (const el of document.querySelectorAll('a')) el.scrollIntoView = vi.fn();

		press('j');
		press('w', { target: document.activeElement });
		expect(first.onclick).toHaveBeenCalledTimes(1);
		expect(second.onclick).not.toHaveBeenCalled();

		document.body.innerHTML = '';
	});

	it('registering from an $effect does not re-trigger that effect', async () => {
		// Regression: register() used to read and write `pageShortcuts` inside the
		// caller's effect, which self-invalidated it — Svelte threw
		// effect_update_depth_exceeded and the whole page rendered empty.
		const { unmount } = render(RegisterHarness, {
			list: BROWSE_SHORTCUTS,
			handlers: { f: vi.fn() }
		});
		await tick();

		expect(shortcuts.pageShortcuts).toHaveLength(BROWSE_SHORTCUTS.length);
		unmount();
		await tick();
		expect(shortcuts.pageShortcuts).toHaveLength(0);
	});

	it('renders a sequence as one label per key', () => {
		expect(keyLabels('g w')).toEqual(['G', 'W']);
		expect(keyLabels('mod+k')[0]).toMatch(/Ctrl \+ K|⌘ \+ K/);
	});
});
