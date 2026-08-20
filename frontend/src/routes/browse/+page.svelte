<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { Unlink } from '@lucide/svelte';

	// A game sold by one shop has nothing merged into it.
	const UNMERGED = {
		label: 'Not merged',
		icon: Unlink,
		title: 'Games only one shop sells',
		condition: { type: 'condition', field: 'store_count', op: 'eq', value: 1 }
	};
</script>

<CatalogBrowser quickFilters={[UNMERGED]} />
