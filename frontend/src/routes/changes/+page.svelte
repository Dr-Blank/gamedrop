<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { History, Clock } from '@lucide/svelte';

	// A listing's first reading is an arrival, so this is "moved at least once".
	const CHANGED = { type: 'change_window' };

	// Relative bounds, so a bookmarked window still means the same window later.
	const WINDOWS = [
		{ label: 'Last 24h', since: '-1d' },
		{ label: 'Last week', since: '-1w' },
		{ label: 'Last month', since: '-1mo' }
	].map(({ label, since }) => ({
		label,
		icon: Clock,
		title: `Any change in the ${label.toLowerCase()}`,
		condition: { type: 'change_window', since, until: 'now' }
	}));
</script>

<CatalogBrowser
	title="Changes"
	icon={History}
	basePath="/changes"
	preset={CHANGED}
	quickFilters={WINDOWS}
	defaultSorts={[{ field: 'last_change_at', dir: 'desc' }]}
	subtitle="Games whose price or stock moved, most recently changed first."
	emptyTitle="No changes"
	emptyHint="Nothing moved in this window."
	countLabel={(n) => `${n} change${n === 1 ? '' : 's'}`}
/>
