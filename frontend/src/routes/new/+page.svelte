<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { Sparkles } from '@lucide/svelte';
</script>

<CatalogBrowser
	title="New arrivals"
	icon={Sparkles}
	basePath="/new"
	saveShelf={false}
	defaultSorts={[{ field: 'first_seen', dir: 'desc' }]}
	subtitle="Games the shops listed most recently."
	emptyTitle="Nothing new"
	emptyHint="New listings show up here after the next sync."
/>
