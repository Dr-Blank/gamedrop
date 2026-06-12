<script>
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { priceHistory, bggSearch, linkBgg } from '$lib/api.js';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		TimeScale,
		Tooltip,
		Legend
	} from 'chart.js';
	import 'chart.js/auto';

	let productId = $derived($page.params.id);
	let data = $state(null);
	let loading = $state(true);
	let chartEl = $state(null);
	let chart = $state(null);

	let bggQuery = $state('');
	let bggResults = $state([]);
	let linking = $state(false);

	async function load() {
		data = await priceHistory(productId);
		loading = false;
	}

	function buildChart() {
		if (!chartEl || !data?.history?.length) return;
		if (chart) chart.destroy();

		const history = [...data.history].reverse();
		const labels = history.map((h) => new Date(h.recorded_at).toLocaleDateString());
		const prices = history.map((h) => h.price);

		chart = new Chart(chartEl, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Price (₹)',
						data: prices,
						borderColor: 'hsl(var(--primary))',
						backgroundColor: 'hsl(var(--primary) / 0.1)',
						fill: true,
						tension: 0.3,
						pointRadius: 4
					}
				]
			},
			options: {
				responsive: true,
				plugins: { legend: { display: false } },
				scales: {
					y: { ticks: { callback: (v) => `₹${v}` } }
				}
			}
		});
	}

	async function searchBgg() {
		if (!data?.product?.title) return;
		bggResults = await bggSearch(bggQuery || data.product.title);
	}

	async function linkGame(bggId) {
		linking = true;
		try {
			await linkBgg(bggId, productId);
			bggResults = [];
			await load();
		} finally {
			linking = false;
		}
	}

	onMount(async () => {
		await load();
		buildChart();
	});

	$effect(() => {
		if (!loading && chartEl) buildChart();
	});
</script>

<div class="space-y-6">
	{#if loading}
		<p class="text-muted-foreground">Loading…</p>
	{:else if !data}
		<p class="text-destructive">Product not found</p>
	{:else}
		<div class="flex items-start justify-between gap-4">
			<div>
				<h1 class="text-2xl font-bold">{data.product.title}</h1>
				<div class="mt-1 flex gap-2">
					<Badge variant="outline">{data.product.store_id}</Badge>
					{#if data.history[0]?.available}
						<Badge class="bg-green-100 text-green-800">In stock</Badge>
					{:else}
						<Badge variant="destructive">OOS</Badge>
					{/if}
					{#if data.history[0]}
						<span class="text-lg font-semibold">₹{data.history[0].price.toFixed(0)}</span>
					{/if}
				</div>
			</div>
			<div class="flex gap-2">
				{#if data.product.url}
					<Button variant="outline" href={data.product.url} target="_blank">View on store ↗</Button>
				{/if}
				{#if data.product.bgg_id}
					<Button
						variant="outline"
						href="https://boardgamegeek.com/boardgame/{data.product.bgg_id}"
						target="_blank"
					>
						BGG ↗
					</Button>
				{/if}
			</div>
		</div>

		<!-- Price chart -->
		{#if data.history.length > 1}
			<Card.Root>
				<Card.Header><Card.Title>Price history</Card.Title></Card.Header>
				<Card.Content>
					<canvas bind:this={chartEl} height="120"></canvas>
				</Card.Content>
			</Card.Root>
		{:else}
			<p class="text-sm text-muted-foreground">
				Not enough price history yet (need 2+ data points).
			</p>
		{/if}

		<!-- Price table -->
		<Card.Root>
			<Card.Header><Card.Title>All snapshots</Card.Title></Card.Header>
			<Card.Content class="max-h-72 overflow-y-auto">
				<table class="w-full text-sm">
					<thead class="sticky top-0 border-b bg-background">
						<tr>
							<th class="py-1 text-left font-medium">Date</th>
							<th class="py-1 text-left font-medium">Price</th>
							<th class="py-1 text-left font-medium">Stock</th>
						</tr>
					</thead>
					<tbody class="divide-y">
						{#each data.history as snap}
							<tr>
								<td class="py-1 text-muted-foreground"
									>{new Date(snap.recorded_at).toLocaleString()}</td
								>
								<td class="py-1 font-semibold">₹{snap.price.toFixed(0)}</td>
								<td class="py-1">
									{#if snap.available}
										<span class="text-green-600">✓</span>
									{:else}
										<span class="text-red-500">✗</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</Card.Content>
		</Card.Root>

		<!-- Link BGG -->
		{#if !data.product.bgg_id}
			<Card.Root>
				<Card.Header><Card.Title>Link to BGG game</Card.Title></Card.Header>
				<Card.Content class="space-y-3">
					<div class="flex gap-2">
						<input
							bind:value={bggQuery}
							placeholder={data.product.title}
							class="flex-1 rounded border bg-background px-3 py-2 text-sm"
							onkeydown={(e) => e.key === 'Enter' && searchBgg()}
						/>
						<Button onclick={searchBgg} variant="outline">Search BGG</Button>
					</div>
					{#if bggResults.length > 0}
						<div class="max-h-48 divide-y overflow-y-auto rounded border">
							{#each bggResults.slice(0, 10) as r}
								<div class="flex items-center justify-between px-3 py-2 text-sm hover:bg-muted/50">
									<span>{r.name} {r.year ? `(${r.year})` : ''}</span>
									<Button size="sm" onclick={() => linkGame(r.bgg_id)} disabled={linking}
										>Link</Button
									>
								</div>
							{/each}
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
