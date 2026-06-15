<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { fade } from 'svelte/transition';
	import { getHome, updateWatchlist } from '$lib/api.js';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import Shelf from '$lib/components/Shelf.svelte';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import { Search, TrendingDown, Sparkles, Tag, Heart, Compass } from '@lucide/svelte';

	let data = $state(/** @type {any} */ (null));
	let loading = $state(true);
	let q = $state('');

	async function load() {
		loading = true;
		try {
			data = await getHome(12);
		} catch (e) {
			toast.error('Failed to load: ' + e.message);
		} finally {
			loading = false;
		}
	}

	function submitSearch() {
		if (q.trim()) goto(`/search?q=${encodeURIComponent(q.trim())}`);
	}

	async function removeWatch(item) {
		await watchlist.toggle(item); // syncs shared state + toasts
		await load();
	}

	async function setTarget(item) {
		const val = prompt('Target price (₹) — blank for any drop:', item.watchlist.target_price ?? '');
		if (val === null) return;
		await updateWatchlist(item.watchlist.id, item.product.id, val ? parseFloat(val) : null);
		toast.success('Target updated');
		await load();
	}

	// drops carry previous_price → synthesize a 2-point history so the card shows a trend.
	const dropHistory = (item) =>
		item.previous_price != null && item.latest_price
			? [{ price: item.latest_price.price }, { price: item.previous_price }]
			: [];

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
			<Shelf
				title="Price drops"
				icon={TrendingDown}
				{loading}
				skeleton={skeletonCard}
				card={() => {}}
			/>
			<Shelf
				title="New additions"
				icon={Sparkles}
				{loading}
				skeleton={skeletonCard}
				card={() => {}}
			/>
			<Shelf title="Top discounts" icon={Tag} {loading} skeleton={skeletonCard} card={() => {}} />
		</div>
	{:else if data}
		<div class="space-y-8" in:fade={{ duration: 150 }}>
			<Shelf
				title="Price drops"
				icon={TrendingDown}
				href="/drops"
				items={data.price_drops}
				empty="No price drops yet — they'll show up here after the next sync."
			>
				{#snippet card(item)}
					<ProductCard {item} variant="browse" history={dropHistory(item)} />
				{/snippet}
			</Shelf>

			<Shelf
				title="New additions"
				icon={Sparkles}
				href="/new"
				items={data.new_additions}
				empty="No products tracked yet."
			>
				{#snippet card(item)}
					<ProductCard {item} variant="browse" />
				{/snippet}
			</Shelf>

			<Shelf
				title="Top discounts"
				icon={Tag}
				href="/browse?sort=discount_pct"
				items={data.top_discounts}
				empty="No active discounts right now."
			>
				{#snippet card(item)}
					<ProductCard {item} variant="browse" />
				{/snippet}
			</Shelf>

			<Shelf
				title="Your watchlist"
				icon={Heart}
				href="/watchlist"
				items={data.watchlist}
				empty="Your watchlist is empty. Browse games to start tracking."
			>
				{#snippet card(item)}
					<ProductCard
						{item}
						variant="watchlist"
						target={item.watchlist?.target_price}
						onremove={() => removeWatch(item)}
						ontarget={() => setTarget(item)}
					/>
				{/snippet}
			</Shelf>
		</div>
	{/if}
</div>
