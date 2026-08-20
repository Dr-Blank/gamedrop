<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { watchlist as watchStore } from '$lib/watchlist.svelte.js';
	import { Heart } from '@lucide/svelte';

	// A watched game that is also hidden contradicts itself; it trails the list
	// so the contradiction is visible and can be settled.
	const WATCHED = { type: 'condition', field: 'is_watched', op: 'eq', value: true };

	// Un-hearting a card takes it off the page at once, without a refetch.
	const stillWatched = (/** @type {any} */ item) =>
		!watchStore.ready || watchStore.has(item.game?.id ?? item.product.game_id);
</script>

<CatalogBrowser
	title="Watchlist"
	icon={Heart}
	basePath="/watchlist"
	preset={WATCHED}
	saveShelf={false}
	showUnmerged={false}
	emptyTitle="Your watchlist is empty"
	emptyHint="Search from the header or browse to start tracking prices."
	countLabel={(n) => `${n} game${n === 1 ? '' : 's'} tracked`}
	stillMatches={stillWatched}
/>
