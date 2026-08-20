<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { hidden as hiddenStore } from '$lib/hidden.svelte.js';
	import { EyeOff } from '@lucide/svelte';

	const IS_HIDDEN = { type: 'condition', field: 'hidden', op: 'eq', value: true };

	const stillHidden = (/** @type {any} */ item) =>
		hiddenStore.has(item.game?.id ?? item.product.game_id);
</script>

<CatalogBrowser
	title="Hidden"
	icon={EyeOff}
	basePath="/hidden"
	preset={IS_HIDDEN}
	hiddenLast={false}
	saveShelf={false}
	showUnmerged={false}
	subtitle="Games you've hidden from browse, drops, new and search. Unhide to bring one back."
	emptyTitle="Nothing hidden"
	emptyHint="Hide a game from any card and it'll show up here."
	countLabel={(n) => `${n} game${n === 1 ? '' : 's'} hidden`}
	stillMatches={stillHidden}
/>
