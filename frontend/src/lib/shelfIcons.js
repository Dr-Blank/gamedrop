import {
	Compass,
	TrendingDown,
	TrendingUp,
	Sparkles,
	Tag,
	Package,
	Star,
	Layers,
	Heart,
	Zap
} from '@lucide/svelte';

/** Shelf.icon holds a lucide icon name — map it to the component. */
export const ICONS = {
	TrendingDown,
	TrendingUp,
	Sparkles,
	Tag,
	Package,
	Star,
	Layers,
	Heart,
	Zap,
	Compass
};

/** @param {string | null | undefined} name */
export const shelfIcon = (name) => ICONS[name ?? ''] ?? Layers;
