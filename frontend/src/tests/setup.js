import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom doesn't implement these browser APIs that components rely on.
class IntersectionObserver {
	observe = vi.fn();
	unobserve = vi.fn();
	disconnect = vi.fn();
	takeRecords = vi.fn(() => []);
}
vi.stubGlobal('IntersectionObserver', IntersectionObserver);

class ResizeObserver {
	observe = vi.fn();
	unobserve = vi.fn();
	disconnect = vi.fn();
}
vi.stubGlobal('ResizeObserver', ResizeObserver);

if (!Element.prototype.scroll) {
	Element.prototype.scroll = () => {};
	Element.prototype.scrollTo = () => {};
}

// Svelte transitions (in:fade) and animations (animate:flip) call
// element.animate / element.getAnimations, which jsdom lacks.
if (!Element.prototype.getAnimations) {
	Element.prototype.getAnimations = () => [];
}
if (!Element.prototype.animate) {
	Element.prototype.animate = () => ({
		cancel: vi.fn(),
		finish: vi.fn(),
		play: vi.fn(),
		pause: vi.fn(),
		reverse: vi.fn(),
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
		currentTime: 0,
		playState: 'finished',
		finished: Promise.resolve(),
		onfinish: null
	});
}

if (!window.matchMedia) {
	vi.stubGlobal(
		'matchMedia',
		vi.fn(() => ({
			matches: false,
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
			addListener: vi.fn(),
			removeListener: vi.fn()
		}))
	);
}
