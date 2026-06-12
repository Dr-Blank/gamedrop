<script>
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { fly, fade } from 'svelte/transition';
	import { priceHistory, bggSearch, bggGame, linkBgg, addWatchlist } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import ProductImage from '$lib/components/ProductImage.svelte';
	import PriceTag from '$lib/components/PriceTag.svelte';
	import StockBadge from '$lib/components/StockBadge.svelte';
	import RatingStats from '$lib/components/RatingStats.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import {
		ArrowLeft,
		ExternalLink,
		Heart,
		Users,
		Clock,
		Baby,
		ChevronDown,
		Link2
	} from '@lucide/svelte';

	let productId = $derived($page.params.id);
	let data = $state(null);
	let bgg = $state(null);
	let loading = $state(true);
	let showAllSnaps = $state(false);

	let bggQuery = $state('');
	let bggResults = $state([]);
	let linking = $state(false);

	async function load() {
		loading = true;
		bgg = null;
		data = await priceHistory(productId);
		loading = false;
		if (data?.product?.bgg_id) {
			bggGame(data.product.bgg_id)
				.then((g) => (bgg = g))
				.catch(() => {});
		}
	}

	const current = $derived(data?.history?.[0] ?? null);
	const imgSrc = $derived(bgg?.image || bgg?.thumbnail || data?.product?.image_url || '');
	const players = $derived(
		bgg?.min_players
			? bgg.min_players === bgg.max_players
				? `${bgg.min_players}`
				: `${bgg.min_players}–${bgg.max_players}`
			: null
	);
	const playtime = $derived(
		bgg?.min_playtime
			? bgg.min_playtime === bgg.max_playtime
				? `${bgg.min_playtime} min`
				: `${bgg.min_playtime}–${bgg.max_playtime} min`
			: null
	);

	async function watch() {
		await addWatchlist(Number(productId), null);
		toast.success('Added to watchlist');
	}

	async function searchBgg() {
		if (!data?.product?.title) return;
		try {
			bggResults = await bggSearch(bggQuery || data.product.title);
		} catch (e) {
			toast.error(e.message);
		}
	}

	async function linkGame(bggId) {
		linking = true;
		try {
			await linkBgg(bggId, productId);
			bggResults = [];
			toast.success('Linked to BGG');
			await load();
		} finally {
			linking = false;
		}
	}

	onMount(load);
</script>

<div class="space-y-6">
	<a
		href="/browse"
		class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
	>
		<ArrowLeft class="size-4" /> Back
	</a>

	{#if loading}
		<div class="grid gap-6 md:grid-cols-[260px_1fr]">
			<Skeleton class="aspect-square w-full rounded-xl" />
			<div class="space-y-3">
				<Skeleton class="h-8 w-2/3" />
				<Skeleton class="h-5 w-40" />
				<Skeleton class="h-20 w-full" />
			</div>
		</div>
		<Skeleton class="h-72 w-full rounded-xl" />
	{:else if !data}
		<p class="text-destructive">Product not found</p>
	{:else}
		<!-- Hero -->
		<div class="grid gap-6 md:grid-cols-[260px_1fr]" in:fade={{ duration: 150 }}>
			<Card.Root class="overflow-hidden p-0">
				<ProductImage src={imgSrc} alt={data.product.title} class="aspect-square w-full" />
			</Card.Root>

			<div class="flex flex-col gap-4">
				<div>
					<div class="mb-1 flex flex-wrap items-center gap-2">
						<Badge variant="outline">{data.product.store_id}</Badge>
						{#if bgg?.year}<Badge variant="outline">{bgg.year}</Badge>{/if}
						<StockBadge available={!!current?.available} />
					</div>
					<h1 class="text-3xl font-bold tracking-tight">{data.product.title}</h1>
					{#if bgg}<div class="mt-2"><RatingStats {bgg} /></div>{/if}
				</div>

				{#if current}
					<div class="flex items-end gap-4">
						<PriceTag price={current.price} compareAt={current.compare_at_price} size="lg" />
					</div>
				{/if}

				<!-- quick facts -->
				{#if bgg && (players || playtime || bgg.min_age)}
					<div class="flex flex-wrap gap-x-6 gap-y-2 text-sm">
						{#if players}
							<span class="inline-flex items-center gap-1.5">
								<Users class="size-4 text-muted-foreground" />
								{players} players
							</span>
						{/if}
						{#if playtime}
							<span class="inline-flex items-center gap-1.5">
								<Clock class="size-4 text-muted-foreground" />
								{playtime}
							</span>
						{/if}
						{#if bgg.min_age}
							<span class="inline-flex items-center gap-1.5">
								<Baby class="size-4 text-muted-foreground" />
								{bgg.min_age}+
							</span>
						{/if}
					</div>
				{/if}

				<div class="mt-auto flex flex-wrap gap-2">
					<Button onclick={watch}>
						<Heart class="size-4" /> Watch
					</Button>
					{#if data.product.url}
						<Button variant="outline" href={data.product.url} target="_blank">
							<ExternalLink class="size-4" /> View on store
						</Button>
					{/if}
					{#if bgg?.bgg_url}
						<Button variant="outline" href={bgg.bgg_url} target="_blank">BGG ↗</Button>
					{/if}
				</div>
			</div>
		</div>

		<!-- Price chart -->
		{#if data.history.length > 1}
			<Card.Root>
				<Card.Header><Card.Title>Price history</Card.Title></Card.Header>
				<Card.Content>
					<PriceChart history={data.history} />
				</Card.Content>
			</Card.Root>
		{:else}
			<Card.Root>
				<Card.Content class="p-6 text-sm text-muted-foreground">
					Not enough price history yet — need at least 2 data points. Check back after the next
					sync.
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Description -->
		{#if bgg?.description}
			<Card.Root>
				<Card.Header><Card.Title>About</Card.Title></Card.Header>
				<Card.Content class="text-sm leading-relaxed text-muted-foreground">
					{bgg.description}{bgg.description.length >= 500 ? '…' : ''}
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Snapshots -->
		<Card.Root>
			<Card.Header class="flex-row items-center justify-between">
				<Card.Title>Price snapshots</Card.Title>
				<span class="text-xs text-muted-foreground">{data.history.length} records</span>
			</Card.Header>
			<Card.Content>
				<div class="overflow-hidden rounded-lg border">
					<table class="w-full text-sm">
						<thead class="bg-muted/50 text-muted-foreground">
							<tr>
								<th class="px-3 py-2 text-left font-medium">Date</th>
								<th class="px-3 py-2 text-right font-medium">Price</th>
								<th class="px-3 py-2 text-center font-medium">Stock</th>
							</tr>
						</thead>
						<tbody class="divide-y">
							{#each showAllSnaps ? data.history : data.history.slice(0, 8) as snap}
								<tr class="transition-colors hover:bg-muted/30">
									<td class="px-3 py-2 text-muted-foreground">
										{new Date(snap.recorded_at).toLocaleString('en-IN', {
											day: 'numeric',
											month: 'short',
											year: 'numeric',
											hour: '2-digit',
											minute: '2-digit'
										})}
									</td>
									<td class="px-3 py-2 text-right font-semibold tabular-nums">
										₹{snap.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
									</td>
									<td class="px-3 py-2 text-center">
										{#if snap.available}
											<span class="text-green-600 dark:text-green-400">●</span>
										{:else}
											<span class="text-destructive">●</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if data.history.length > 8}
					<button
						onclick={() => (showAllSnaps = !showAllSnaps)}
						class="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
					>
						<ChevronDown class="size-4 transition-transform {showAllSnaps ? 'rotate-180' : ''}" />
						{showAllSnaps ? 'Show less' : `Show all ${data.history.length}`}
					</button>
				{/if}
			</Card.Content>
		</Card.Root>

		<!-- Link BGG -->
		{#if !data.product.bgg_id}
			<Card.Root>
				<Card.Header>
					<Card.Title class="flex items-center gap-2">
						<Link2 class="size-4" /> Link to BoardGameGeek
					</Card.Title>
				</Card.Header>
				<Card.Content class="space-y-3">
					<div class="flex gap-2">
						<input
							bind:value={bggQuery}
							placeholder={data.product.title}
							class="h-9 flex-1 rounded-lg border bg-background px-3 text-sm"
							onkeydown={(e) => e.key === 'Enter' && searchBgg()}
						/>
						<Button onclick={searchBgg} variant="outline">Search BGG</Button>
					</div>
					{#if bggResults.length > 0}
						<div
							class="max-h-56 divide-y overflow-y-auto rounded-lg border"
							transition:fly={{ y: -8 }}
						>
							{#each bggResults.slice(0, 10) as r}
								<div class="flex items-center justify-between px-3 py-2 text-sm hover:bg-muted/40">
									<span>{r.name} {r.year ? `(${r.year})` : ''}</span>
									<Button size="sm" onclick={() => linkGame(r.bgg_id)} disabled={linking}>
										Link
									</Button>
								</div>
							{/each}
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
