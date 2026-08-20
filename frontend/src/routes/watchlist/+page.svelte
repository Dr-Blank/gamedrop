<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { Heart } from '@lucide/svelte';

	// Hidden games are included on purpose: a watched game that is also hidden
	// contradicts itself, and this is where it can be settled.
	const WATCHED = { type: 'condition', field: 'is_watched', op: 'eq', value: true };
</script>

<CatalogBrowser
	title="Watchlist"
	icon={Heart}
	basePath="/watchlist"
	preset={WATCHED}
	includeHidden
	saveShelf={false}
	showUnmerged={false}
	emptyTitle="Your watchlist is empty"
	emptyHint="Search from the header or browse to start tracking prices."
	countLabel={(n) => `${n} game${n === 1 ? '' : 's'} tracked`}
/>
