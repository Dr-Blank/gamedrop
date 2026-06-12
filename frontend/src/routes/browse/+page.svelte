<script>
	import { onMount } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Card from '$lib/components/ui/card';
	import { addWatchlist } from '$lib/api.js';

	let stores = $state([]);
	let items = $state([]);
	let loading = $state(false);
	let page = $state(1);
	let hasMore = $state(true);

	let filters = $state({
		q: '',
		store_id: '',
		min_price: '',
		max_price: '',
		in_stock: false,
		has_bgg: false,
		min_bgg_rating: '',
		sort: 'title'
	});

	async function fetchStores() {
		const res = await fetch('/api/browse/stores').then((r) => r.json());
		stores = res;
	}

	function buildQuery(p = 1) {
		const params = new URLSearchParams({ page: String(p), limit: '48' });
		if (filters.q) params.set('q', filters.q);
		if (filters.store_id) params.set('store_id', filters.store_id);
		if (filters.min_price) params.set('min_price', filters.min_price);
		if (filters.max_price) params.set('max_price', filters.max_price);
		if (filters.in_stock) params.set('in_stock', 'true');
		if (filters.has_bgg) params.set('has_bgg', 'true');
		if (filters.min_bgg_rating) params.set('min_bgg_rating', filters.min_bgg_rating);
		params.set('sort', filters.sort);
		return params;
	}

	async function search(reset = true) {
		loading = true;
		if (reset) {
			page = 1;
			items = [];
		}
		const res = await fetch(`/api/browse?${buildQuery(page)}`).then((r) => r.json());
		items = reset ? res.items : [...items, ...res.items];
		hasMore = res.items.length === 48;
		loading = false;
	}

	async function loadMore() {
		page += 1;
		await search(false);
	}

	async function watch(product) {
		await addWatchlist(product.id, null);
	}

	function stars(rating) {
		if (!rating) return '—';
		return parseFloat(rating).toFixed(1);
	}

	onMount(async () => {
		await fetchStores();
		await search();
	});
</script>

<div class="space-y-4">
	<h1 class="text-2xl font-bold">Browse</h1>

	<!-- Filters -->
	<Card.Root>
		<Card.Content class="pt-4">
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				<Input
					bind:value={filters.q}
					placeholder="Search name…"
					onkeydown={(e) => e.key === 'Enter' && search()}
				/>
				<select
					bind:value={filters.store_id}
					class="rounded border bg-background px-3 py-2 text-sm"
				>
					<option value="">All stores</option>
					{#each stores as s}<option value={s.id}>{s.name}</option>{/each}
				</select>
				<div class="flex gap-2">
					<Input bind:value={filters.min_price} placeholder="Min ₹" type="number" />
					<Input bind:value={filters.max_price} placeholder="Max ₹" type="number" />
				</div>
				<select bind:value={filters.sort} class="rounded border bg-background px-3 py-2 text-sm">
					<option value="title">Sort: Name</option>
					<option value="price_asc">Sort: Price ↑</option>
					<option value="price_desc">Sort: Price ↓</option>
				</select>
			</div>
			<div class="mt-3 flex items-center gap-6">
				<label class="flex cursor-pointer items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={filters.in_stock} class="rounded" />
					In stock only
				</label>
				<label class="flex cursor-pointer items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={filters.has_bgg} class="rounded" />
					Has BGG data
				</label>
				<div class="flex items-center gap-2 text-sm">
					<span>Min BGG rating:</span>
					<Input
						bind:value={filters.min_bgg_rating}
						type="number"
						step="0.5"
						min="1"
						max="10"
						class="w-20"
						placeholder="e.g. 7"
					/>
				</div>
				<Button onclick={() => search()}>Apply</Button>
				<Button
					variant="ghost"
					onclick={() => {
						filters = {
							q: '',
							store_id: '',
							min_price: '',
							max_price: '',
							in_stock: false,
							has_bgg: false,
							min_bgg_rating: '',
							sort: 'title'
						};
						search();
					}}
				>
					Reset
				</Button>
			</div>
		</Card.Content>
	</Card.Root>

	<!-- Results grid -->
	{#if loading && items.length === 0}
		<p class="text-muted-foreground">Loading…</p>
	{:else if items.length === 0}
		<p class="text-muted-foreground">No results. Try adjusting filters.</p>
	{:else}
		<div class="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
			{#each items as item}
				<Card.Root class="flex flex-col">
					{#if item.bgg?.thumbnail}
						<img
							src={item.bgg.thumbnail}
							alt={item.product.title}
							class="h-32 w-full rounded-t-lg bg-muted/30 object-contain p-2"
						/>
					{:else}
						<div
							class="flex h-32 w-full items-center justify-center rounded-t-lg bg-muted/30 text-4xl"
						>
							🎲
						</div>
					{/if}

					<Card.Content class="flex flex-1 flex-col gap-2 pt-3 pb-3">
						<div class="line-clamp-2 text-sm leading-tight font-medium">
							{item.product.title}
						</div>

						<div class="flex flex-wrap items-center gap-2">
							{#if item.latest_price}
								<span class="text-base font-bold">₹{item.latest_price.price.toFixed(0)}</span>
								{#if item.latest_price.compare_at_price > item.latest_price.price}
									<span class="text-xs text-muted-foreground line-through">
										₹{item.latest_price.compare_at_price.toFixed(0)}
									</span>
								{/if}
							{/if}
							{#if item.latest_price?.available}
								<Badge class="bg-green-100 text-xs text-green-800">In stock</Badge>
							{:else}
								<Badge variant="destructive" class="text-xs">OOS</Badge>
							{/if}
						</div>

						{#if item.bgg}
							<div class="flex gap-3 text-xs text-muted-foreground">
								<span>⭐ {stars(item.bgg.avg_rating)}</span>
								{#if item.bgg.rank}<span>#{item.bgg.rank}</span>{/if}
								{#if item.bgg.avg_weight}<span>⚖️ {parseFloat(item.bgg.avg_weight).toFixed(1)}</span
									>{/if}
							</div>
						{/if}

						<div class="mt-auto flex flex-wrap gap-1 pt-1">
							{#if item.product.url}
								<Button
									size="sm"
									variant="outline"
									href={item.product.url}
									target="_blank"
									class="flex-1 text-xs"
								>
									Store ↗
								</Button>
							{/if}
							{#if item.bgg?.bgg_url}
								<Button
									size="sm"
									variant="outline"
									href={item.bgg.bgg_url}
									target="_blank"
									class="flex-1 text-xs"
								>
									BGG ↗
								</Button>
							{/if}
							<Button size="sm" onclick={() => watch(item.product)} class="flex-1 text-xs">
								+ Watch
							</Button>
						</div>
					</Card.Content>
				</Card.Root>
			{/each}
		</div>

		{#if hasMore}
			<div class="flex justify-center pt-4">
				<Button variant="outline" onclick={loadMore} disabled={loading}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	{/if}
</div>
