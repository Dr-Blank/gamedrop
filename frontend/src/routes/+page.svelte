<script>
	import { onMount } from 'svelte';
	import { getWatchlist, removeWatchlist, updateWatchlist, priceSearch, addWatchlist } from '$lib/api.js';
	import * as Card from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';

	let watchlist = $state([]);
	let loading = $state(true);
	let error = $state('');

	// search to add
	let searchQuery = $state('');
	let searchResults = $state([]);
	let searching = $state(false);
	let targetPrice = $state('');

	async function load() {
		try {
			watchlist = await getWatchlist();
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function remove(id) {
		await removeWatchlist(id);
		await load();
	}

	async function setTarget(item) {
		const val = prompt('Set target price (₹), leave blank for any drop:', item.watchlist.target_price ?? '');
		if (val === null) return;
		await updateWatchlist(item.watchlist.id, item.watchlist.product_id, val ? parseFloat(val) : null);
		await load();
	}

	async function search() {
		if (!searchQuery.trim()) return;
		searching = true;
		try {
			searchResults = await priceSearch(searchQuery);
		} finally {
			searching = false;
		}
	}

	async function addToWatchlist(product) {
		await addWatchlist(product.id, targetPrice ? parseFloat(targetPrice) : null);
		searchQuery = '';
		searchResults = [];
		targetPrice = '';
		await load();
	}

	onMount(load);
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold">Watchlist</h1>
	</div>

	<!-- Add to watchlist -->
	<Card.Root>
		<Card.Header>
			<Card.Title>Add to watchlist</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-3">
			<div class="flex gap-2">
				<Input
					bind:value={searchQuery}
					placeholder="Search game name…"
					onkeydown={(e) => e.key === 'Enter' && search()}
				/>
				<Input bind:value={targetPrice} placeholder="Target ₹ (optional)" class="w-40" />
				<Button onclick={search} disabled={searching}>
					{searching ? 'Searching…' : 'Search'}
				</Button>
			</div>

			{#if searchResults.length > 0}
				<div class="border rounded-md divide-y max-h-64 overflow-y-auto">
					{#each searchResults as r}
						<div class="flex items-center justify-between px-4 py-2 text-sm hover:bg-muted/50">
							<div>
								<div class="font-medium">{r.product.title}</div>
								<div class="text-muted-foreground text-xs">{r.product.store_id}</div>
							</div>
							<div class="flex items-center gap-3">
								{#if r.latest_price}
									<span class="font-semibold">₹{r.latest_price.price.toFixed(0)}</span>
									{#if !r.latest_price.available}
										<Badge variant="destructive">OOS</Badge>
									{/if}
								{/if}
								<Button size="sm" onclick={() => addToWatchlist(r.product)}>Watch</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Watchlist table -->
	{#if loading}
		<p class="text-muted-foreground">Loading…</p>
	{:else if error}
		<p class="text-destructive">Error: {error}</p>
	{:else if watchlist.length === 0}
		<p class="text-muted-foreground">No items on watchlist. Search above to add games.</p>
	{:else}
		<Card.Root>
			<Table.Root>
				<Table.Header>
					<Table.Row>
						<Table.Head>Game</Table.Head>
						<Table.Head>Store</Table.Head>
						<Table.Head>Current price</Table.Head>
						<Table.Head>Target</Table.Head>
						<Table.Head>Stock</Table.Head>
						<Table.Head></Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each watchlist as item}
						<Table.Row>
							<Table.Cell class="font-medium">
								<a href={item.product.url} target="_blank" class="hover:underline">
									{item.product.title}
								</a>
								{#if item.product.bgg_id}
									<a
										href="https://boardgamegeek.com/boardgame/{item.product.bgg_id}"
										target="_blank"
										class="ml-2 text-xs text-muted-foreground hover:underline"
									>BGG ↗</a>
								{/if}
							</Table.Cell>
							<Table.Cell class="text-sm text-muted-foreground">{item.store?.name ?? item.product.store_id}</Table.Cell>
							<Table.Cell>
								{#if item.latest_price}
									<span class="font-semibold">₹{item.latest_price.price.toFixed(0)}</span>
									{#if item.latest_price.compare_at_price && item.latest_price.compare_at_price > item.latest_price.price}
										<span class="ml-1 text-xs line-through text-muted-foreground">
											₹{item.latest_price.compare_at_price.toFixed(0)}
										</span>
									{/if}
								{:else}
									<span class="text-muted-foreground">—</span>
								{/if}
							</Table.Cell>
							<Table.Cell>
								<button
									class="text-sm hover:underline"
									onclick={() => setTarget(item)}
								>
									{item.watchlist.target_price ? `₹${item.watchlist.target_price.toFixed(0)}` : 'any drop'}
								</button>
							</Table.Cell>
							<Table.Cell>
								{#if item.latest_price?.available}
									<Badge class="bg-green-100 text-green-800">In stock</Badge>
								{:else}
									<Badge variant="destructive">OOS</Badge>
								{/if}
							</Table.Cell>
							<Table.Cell>
								<div class="flex gap-2">
									<Button size="sm" variant="outline" href="/prices/{item.product.id}">
										History
									</Button>
									<Button
										size="sm"
										variant="destructive"
										onclick={() => remove(item.watchlist.id)}
									>Remove</Button>
								</div>
							</Table.Cell>
						</Table.Row>
					{/each}
				</Table.Body>
			</Table.Root>
		</Card.Root>
	{/if}
</div>
