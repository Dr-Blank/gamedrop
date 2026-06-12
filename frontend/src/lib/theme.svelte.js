import { browser } from '$app/environment';

const STORAGE_KEY = 'gd-theme';

/** @typedef {'light' | 'dark' | 'system'} ThemeMode */

function systemPrefersDark() {
	return browser && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

class ThemeState {
	/** @type {ThemeMode} */
	mode = $state('system');

	constructor() {
		if (browser) {
			const saved = /** @type {ThemeMode | null} */ (localStorage.getItem(STORAGE_KEY));
			this.mode = saved ?? 'system';
		}
	}

	/** Resolved boolean: is dark currently applied. */
	get isDark() {
		return this.mode === 'dark' || (this.mode === 'system' && systemPrefersDark());
	}

	/** @param {ThemeMode} next */
	set(next) {
		this.mode = next;
		if (browser) {
			localStorage.setItem(STORAGE_KEY, next);
			this.apply();
		}
	}

	/** Cycle light → dark → system. */
	toggle() {
		this.set(this.isDark ? 'light' : 'dark');
	}

	apply() {
		if (!browser) return;
		document.documentElement.classList.toggle('dark', this.isDark);
		const meta = document.querySelector('meta[name="theme-color"]');
		if (meta) meta.setAttribute('content', this.isDark ? '#0a0a0a' : '#ffffff');
	}
}

export const theme = new ThemeState();
