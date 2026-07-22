/**
 * Global keyboard shortcuts.
 *
 * One registry drives both the key handler and the `?` help sheet, so a
 * shortcut can never be live but undocumented. Pages add their own with
 * `shortcuts.register()` inside an `$effect`; the returned cleanup removes
 * them again on navigation.
 */
import { untrack } from 'svelte';
import { goto } from '$app/navigation';
import { DROPS_URL, NEW_URL } from './browse.js';
import { theme } from './theme.svelte.js';
import { moveCursor, cardAction } from './cardCursor.js';

/**
 * @typedef {object} Shortcut
 * @property {string} keys   Space-separated sequence, e.g. 'g h' or 'mod+k'.
 * @property {string} label  Shown in the help sheet.
 * @property {string} group  Help-sheet section.
 * @property {() => void} [run]
 */

const CHORD_TIMEOUT_MS = 1500;

/** Elements that own the keyboard — plain keys must reach them untouched. */
function isTyping(target) {
	if (!(target instanceof HTMLElement)) return false;
	return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

/** Normalize a keydown into a token like 'g', '/', 'mod+k'. */
function tokenFor(e) {
	const key = e.key.toLowerCase();
	if (['shift', 'control', 'alt', 'meta'].includes(key)) return '';
	let token = key === ' ' ? 'space' : key;
	if (e.altKey) token = `alt+${token}`;
	if (e.metaKey || e.ctrlKey) token = `mod+${token}`;
	return token;
}

class ShortcutState {
	helpOpen = $state(false);
	/** Chord prefix already typed, e.g. 'g' — surfaced as an on-screen hint. */
	pending = $state('');
	/** @type {Shortcut[]} */
	pageShortcuts = $state([]);

	/** @type {(() => void) | null} */
	#focusSearch = null;
	#timer = 0;
	#nextRegistration = 0;

	/** Layout hands us the header search input. */
	registerSearchFocus(fn) {
		this.#focusSearch = fn;
		return () => {
			if (this.#focusSearch === fn) this.#focusSearch = null;
		};
	}

	focusSearch() {
		this.#focusSearch?.();
	}

	/**
	 * Activate page-scoped shortcuts. The definitions live in the catalog below
	 * so /shortcuts can list them from anywhere; the page supplies only the
	 * handlers. Returns a cleanup function.
	 * @param {Shortcut[]} list
	 * @param {Record<string, () => void>} handlers  keyed by `keys`
	 */
	register(list, handlers = {}) {
		// Tag by registration id: `pageShortcuts` is a $state array, so what
		// comes back out is a proxy and identity comparison never matches.
		const id = ++this.#nextRegistration;
		const bound = list.map((s) => ({ ...s, run: handlers[s.keys] ?? s.run, reg: id }));
		// untrack: pages call this from an $effect, and reading the list we are
		// about to write would make that effect re-run itself forever.
		untrack(() => {
			this.pageShortcuts = [...this.pageShortcuts, ...bound];
		});
		return () =>
			untrack(() => {
				this.pageShortcuts = this.pageShortcuts.filter((s) => s.reg !== id);
			});
	}

	/** @returns {Shortcut[]} */
	get all() {
		return [...GLOBAL_SHORTCUTS, ...this.pageShortcuts];
	}

	#clearPending() {
		clearTimeout(this.#timer);
		this.pending = '';
	}

	/** @param {KeyboardEvent} e */
	handle(e) {
		const token = tokenFor(e);
		if (!token) return;

		if (token === 'escape') {
			this.#clearPending();
			if (this.helpOpen) this.helpOpen = false;
			if (isTyping(e.target)) /** @type {HTMLElement} */ (e.target).blur();
			return;
		}

		// The help sheet swallows plain keys so `g h` can't navigate behind it.
		if (this.helpOpen && !token.startsWith('mod+')) return;

		// Plain keys belong to whatever the user is typing in; combos still work.
		const typing = isTyping(e.target);
		if (typing && !token.startsWith('mod+') && !token.startsWith('alt+')) return;

		const seq = this.pending ? `${this.pending} ${token}` : token;
		// `run`-less entries are documentation for browser/native behaviour
		// (Enter on a focused card) — matching them would swallow the key.
		const match = this.all.find((s) => s.keys === seq && s.run);
		if (match) {
			e.preventDefault();
			this.#clearPending();
			match.run?.();
			return;
		}

		if (this.all.some((s) => s.keys.startsWith(`${seq} `))) {
			e.preventDefault();
			clearTimeout(this.#timer);
			this.pending = seq;
			this.#timer = setTimeout(() => (this.pending = ''), CHORD_TIMEOUT_MS);
			return;
		}

		this.#clearPending();
	}
}

export const shortcuts = new ShortcutState();

/** @type {Shortcut[]} */
export const GLOBAL_SHORTCUTS = [
	{
		keys: '/',
		label: 'Focus search',
		group: 'General',
		run: () => shortcuts.focusSearch()
	},
	{
		keys: 'mod+k',
		label: 'Focus search',
		group: 'General',
		run: () => shortcuts.focusSearch()
	},
	{
		// Overrides the browser's find-in-page, which is near-useless here
		// because the list is paginated — most matches are not in the DOM yet.
		keys: 'mod+f',
		label: 'Focus search',
		group: 'General',
		run: () => shortcuts.focusSearch()
	},
	{
		// `?` is already the shifted key — tokens carry no separate shift flag.
		keys: '?',
		label: 'Show shortcuts',
		group: 'General',
		run: () => (shortcuts.helpOpen = !shortcuts.helpOpen)
	},
	{
		keys: 'mod+/',
		label: 'Show shortcuts',
		group: 'General',
		run: () => (shortcuts.helpOpen = !shortcuts.helpOpen)
	},
	{ keys: 't', label: 'Toggle theme', group: 'General', run: () => theme.toggle() },
	{
		keys: 'escape',
		label: 'Close / leave the search box',
		group: 'General'
	},
	{ keys: 'g h', label: 'Home', group: 'Go to', run: () => goto('/') },
	{ keys: 'g b', label: 'Browse', group: 'Go to', run: () => goto('/browse') },
	{ keys: 'g d', label: 'Price drops', group: 'Go to', run: () => goto(DROPS_URL) },
	{ keys: 'g n', label: 'New additions', group: 'Go to', run: () => goto(NEW_URL) },
	{ keys: 'g w', label: 'Watchlist', group: 'Go to', run: () => goto('/watchlist') },
	{ keys: 'g s', label: 'Stores', group: 'Go to', run: () => goto('/stores') },
	{ keys: 'g a', label: 'Alerts', group: 'Go to', run: () => goto('/notifications') },
	{ keys: 'g i', label: 'Hidden', group: 'Go to', run: () => goto('/hidden') },
	{ keys: 'g g', label: 'BGG link', group: 'Go to', run: () => goto('/bgg-link') },
	{ keys: 'g l', label: 'Logs', group: 'Go to', run: () => goto('/logs') },
	{ keys: 'g ,', label: 'Settings', group: 'Go to', run: () => goto('/settings') },
	{ keys: 'g k', label: 'Shortcuts', group: 'Go to', run: () => goto('/shortcuts') },
	{ keys: 'j', label: 'Next card', group: 'Cards', run: () => moveCursor(1) },
	{ keys: 'k', label: 'Previous card', group: 'Cards', run: () => moveCursor(-1) },
	{ keys: 'w', label: 'Watch / unwatch card', group: 'Cards', run: () => cardAction('watch') },
	{ keys: 'x', label: 'Hide card', group: 'Cards', run: () => cardAction('hide') },
	// No `run`: the card is a link, so Enter already opens it.
	{ keys: 'enter', label: 'Open focused card', group: 'Cards' }
];

/**
 * Page-scoped definitions. Declared here rather than inline in the page so the
 * /shortcuts reference can list them while you are somewhere else.
 * @type {Shortcut[]}
 */
export const BROWSE_SHORTCUTS = [
	{ keys: 'f', label: 'Toggle filter panel', group: 'Browse' },
	{ keys: 'r', label: 'Reset filters and sorts', group: 'Browse' },
	{ keys: 'mod+enter', label: 'Apply filters', group: 'Browse' },
	{ keys: '.', label: 'Filter by store', group: 'Browse' }
];

/** @type {Shortcut[]} */
export const NOTIFICATION_SHORTCUTS = [{ keys: 'u', label: 'Mark all as read', group: 'Alerts' }];

/** Everything that exists, live or not — the /shortcuts page renders this. */
export const SHORTCUT_CATALOG = [
	...GLOBAL_SHORTCUTS,
	...BROWSE_SHORTCUTS,
	...NOTIFICATION_SHORTCUTS
];

/** Pretty-print 'mod+k' / 'g h' for the help sheet. */
export function keyLabels(keys) {
	const mod =
		typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform ?? '')
			? '⌘'
			: 'Ctrl';
	return keys.split(' ').map((part) =>
		part
			.split('+')
			.map((k) => {
				if (k === 'mod') return mod;
				if (k === 'escape') return 'Esc';
				if (k === 'shift') return 'Shift';
				if (k === 'alt') return 'Alt';
				return k.length === 1 ? k.toUpperCase() : k;
			})
			.join(' + ')
	);
}
