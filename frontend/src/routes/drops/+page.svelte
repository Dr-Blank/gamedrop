<script>
	import { onMount } from 'svelte';
	import { feedDrops } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Button } from '$lib/components/ui/button';
	import { TrendingDown } from '@lucide/svelte';

	let items = $state([]);
	let loading = $state(true);
	let page = $state(1);
	let hasMore = $state(true);
	let inStock = $state(false);

	const LIMIT = 24;

	async function load(reset = true) {
		loading = true;
		if (reset) {
			page = 1;
			items = [];
		}
		try {
			const res = await feedDrops(page, LIMIT, inStock);
			items = reset ? res.items : [...items, ...res.items];
			hasMore = res.items.length === LIMIT;
		} catch (e) {
			toast.error(e.message);
		} finally {
			loading = false;
		}
	}

	async function more() {
		page += 1;
		await load(false);
	}

	const history = (item) =>
		item.previous_price != null && item.latest_price
			? [{ price: item.latest_price.price }, { price: item.previous_price }]
			: [];

	onMount(() => load());
</script>

<div class="space-y-5">
	<div class="flex items-center justify-between gap-3">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<TrendingDown class="size-6 text-primary" /> Price drops
			</h1>
			<p class="text-sm text-muted-foreground">Games cheaper than their last recorded price.</p>
		</div>
		<label class="flex cursor-pointer items-center gap-2 text-sm">
			<input
				type="checkbox"
				bind:checked={inStock}
				onchange={() => load()}
				class="size-4 rounded"
			/>
			In stock only
		</label>
	</div>

	{#if loading && items.length === 0}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each Array(12) as _}
				<div class="space-y-2 rounded-xl border p-3">
					<Skeleton class="aspect-[4/3] w-full" />
					<Skeleton class="h-4 w-3/4" />
					<Skeleton class="h-4 w-1/2" />
				</div>
			{/each}
		</div>
	{:else if items.length === 0}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<TrendingDown class="size-10 text-muted-foreground/40" />
			<p class="font-medium">No price drops yet</p>
			<p class="text-sm text-muted-foreground">Check back after the next store sync.</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each items as item (item.product.id)}
				<ProductCard {item} variant="browse" history={history(item)} />
			{/each}
		</div>
		{#if hasMore}
			<div class="flex justify-center pt-2">
				<Button variant="outline" onclick={more} disabled={loading}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	{/if}
</div>
