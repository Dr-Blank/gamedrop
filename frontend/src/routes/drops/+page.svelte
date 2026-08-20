<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { TrendingDown, PackageCheck } from '@lucide/svelte';

	// Cheaper than the previous recorded price — the % is negative on a drop.
	const DROPPED = { type: 'condition', field: 'price_pct_change', op: 'lt', value: 0 };

	const IN_STOCK = {
		label: 'In stock',
		icon: PackageCheck,
		title: 'Only drops you can buy right now',
		condition: { type: 'condition', field: 'available', op: 'eq', value: true }
	};
</script>

<CatalogBrowser
	title="Price drops"
	icon={TrendingDown}
	basePath="/drops"
	preset={DROPPED}
	saveShelf={false}
	quickFilters={[IN_STOCK]}
	defaultSorts={[{ field: 'price_pct_change', dir: 'asc' }]}
	subtitle="Games cheaper than their last recorded price."
	emptyTitle="No drops"
	emptyHint="Prices held steady since the last sync."
	countLabel={(n) => `${n} drop${n === 1 ? '' : 's'}`}
/>
