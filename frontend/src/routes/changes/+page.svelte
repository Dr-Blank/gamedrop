<script>
	import CatalogBrowser from '$lib/components/CatalogBrowser.svelte';
	import { History, Clock } from '@lucide/svelte';

	// Relative bounds, so a bookmarked window still means the same window later.
	// `include_new` keeps a shop's fresh listings in — an arrival inside the
	// window is news, even though the listing has nothing to compare against.
	const WINDOWS = [
		{ label: 'Last 24h', since: '-1d' },
		{ label: 'Last week', since: '-1w' },
		{ label: 'Last month', since: '-1mo' }
	].map(({ label, since }) => ({
		label,
		icon: Clock,
		title: `Anything added or moved in the ${label.toLowerCase()}`,
		condition: { type: 'change_window', since, until: 'now', include_new: true }
	}));

	// The feed needs bounds to mean anything, so it opens on a week of them.
	const DEFAULT_WINDOW = WINDOWS[1].condition;
</script>

<CatalogBrowser
	title="Changes"
	icon={History}
	basePath="/changes"
	quickFilters={WINDOWS}
	defaultFilters={[DEFAULT_WINDOW]}
	defaultSorts={[{ field: 'recorded_at', dir: 'desc' }]}
	subtitle="Games a shop added, repriced or restocked — most recent first."
	emptyTitle="No changes"
	emptyHint="Nothing moved in this window."
	countLabel={(n) => `${n} change${n === 1 ? '' : 's'}`}
/>
