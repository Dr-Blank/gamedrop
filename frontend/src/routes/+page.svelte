<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { fade } from 'svelte/transition';
	import { shelvesPreview, getWatchlist } from '$lib/api.js';
	import { browseUrl } from '$lib/browse.js';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import Shelf from '$lib/components/Shelf.svelte';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import {
		Search,
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

	// Map icon name strings → Svelte components
	const ICONS = {
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

	let shelvesList = $state(/** @type {any[]} */ ([]));
	let watchlistItems = $state(/** @type {any[]} */ ([]));
	let loading = $state(true);
	let q = $state('');

	function shelfBrowseUrl(shelf) {
		return browseUrl({
			filters: shelf.filters ? JSON.parse(shelf.filters) : null,
			sorts: shelf.sorts ? JSON.parse(shelf.sorts) : []
		});
	}

	async function load() {
		loading = true;
		try {
			const [preview, wl] = await Promise.all([shelvesPreview(8), getWatchlist()]);
			shelvesList = preview;
			watchlistItems = wl;
		} catch (e) {
			toast.error('Failed to load: ' + e.message);
		} finally {
			loading = false;
		}
	}

	function submitSearch() {
		if (q.trim()) goto(`/search?q=${encodeURIComponent(q.trim())}`);
	}

	onMount(load);
</script>

<div class="space-y-8">
	<!-- Hero -->
	<section
		class="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-background to-background p-6 sm:p-10"
	>
		<div class="relative z-10 max-w-2xl space-y-3">
			<h1 class="text-3xl font-bold tracking-tight sm:text-4xl">
				Never overpay for a board game again
			</h1>
			<p class="text-muted-foreground">
				Track prices across stores, catch every drop, and pounce when it hits your target.
			</p>
			<form
				onsubmit={(e) => {
					e.preventDefault();
					submitSearch();
				}}
				class="flex max-w-md gap-2 pt-1"
			>
				<div class="relative flex-1">
					<Search
						class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
					/>
					<Input bind:value={q} placeholder="Search any game…" class="h-11 pl-9" />
				</div>
				<Button type="submit" size="lg" class="h-11">Search</Button>
			</form>
		</div>
		<Compass
			class="pointer-events-none absolute -right-8 -bottom-8 size-48 text-primary/5"
			strokeWidth={1}
		/>
	</section>

	{#snippet skeletonCard()}
		<div class="space-y-2 rounded-xl border p-3">
			<Skeleton class="aspect-[4/3] w-full" />
			<Skeleton class="h-4 w-3/4" />
			<Skeleton class="h-4 w-1/2" />
		</div>
	{/snippet}

	{#if loading}
		<div class="space-y-8" in:fade>
			{#each Array(4) as _}
				<Shelf title="Loading…" loading={true} skeleton={skeletonCard} card={() => {}} />
			{/each}
		</div>
	{:else}
		<div class="space-y-8" in:fade={{ duration: 150 }}>
			<!-- Dynamic shelves from backend -->
			{#each shelvesList as { shelf, items }}
				{@const Icon = ICONS[shelf.icon] ?? Layers}
				<Shelf
					title={shelf.name}
					icon={Icon}
					href={shelfBrowseUrl(shelf)}
					{items}
					empty="Nothing here yet."
				>
					{#snippet card(item)}
						<ProductCard {item} variant="browse" />
					{/snippet}
				</Shelf>
			{/each}

			<!-- Watchlist (special — not a filter shelf) -->
			{#if watchlistItems.length > 0}
				<Shelf
					title="Your watchlist"
					icon={Heart}
					href="/watchlist"
					items={watchlistItems.slice(0, 8)}
					empty="Your watchlist is empty."
				>
					{#snippet card(item)}
						<ProductCard
							{item}
							variant="watchlist"
							target={item.watchlist?.target_price}
							onremove={() => watchlist.toggle(item).then(load)}
						/>
					{/snippet}
				</Shelf>
			{/if}

			<!-- Browse CTA -->
			<div class="flex items-center justify-center py-4">
				<Button href="/browse" variant="outline" size="lg">
					<Compass class="size-4" /> Browse all games
				</Button>
			</div>
		</div>
	{/if}
</div>
