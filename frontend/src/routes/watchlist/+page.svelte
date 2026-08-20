<script>
	import { onMount, tick } from 'svelte';
	import { fly } from 'svelte/transition';
	import { beforeNavigate, afterNavigate } from '$app/navigation';
	import { flip } from 'svelte/animate';
	import { getWatchlist, priceSearch, addWatchlist, priceHistory } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import { watchlist as watchStore } from '$lib/watchlist.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import StockBadge from '$lib/components/StockBadge.svelte';
	import PriceTag from '$lib/components/PriceTag.svelte';
	import { Search, Plus, Heart } from '@lucide/svelte';

	let watchlist = $state([]);
	let loading = $state(true);
	let error = $state('');
	let sortBy = $state('name_asc');
	let priceHistories = $state(/** @type {Record<number, any[]>} */ ({}));

	const sortOptions = [
		{ v: 'name_asc', l: 'Name A→Z' },
		{ v: 'name_desc', l: 'Name Z→A' },
		{ v: 'price_asc', l: 'Price low→high' },
		{ v: 'price_desc', l: 'Price high→low' },
		{ v: 'stock_first', l: 'In stock first' }
	];

	// The heart lives on the card, so the store — not a refetch — decides what
	// stays on screen.
	let watched = $derived(
		watchStore.ready ? watchlist.filter((item) => watchStore.has(item.game.id)) : watchlist
	);

	let sortedWatchlist = $derived(
		[...watched].sort((a, b) => {
			if (sortBy === 'name_asc') return a.game.title.localeCompare(b.game.title);
			if (sortBy === 'name_desc') return b.game.title.localeCompare(a.game.title);
			if (sortBy === 'price_asc')
				return (a.latest_price?.price ?? Infinity) - (b.latest_price?.price ?? Infinity);
			if (sortBy === 'price_desc')
				return (b.latest_price?.price ?? 0) - (a.latest_price?.price ?? 0);
			if (sortBy === 'stock_first')
				return (a.latest_price?.available ? 0 : 1) - (b.latest_price?.available ? 0 : 1);
			return 0;
		})
	);

	// search to add
	let searchQuery = $state('');
	let searchResults = $state([]);
	let searching = $state(false);
	let targetPrice = $state('');

	async function load() {
		try {
			watchlist = await getWatchlist();
			const histories = await Promise.all(
				watchlist.map((item) => priceHistory(item.product.id).catch(() => ({ history: [] })))
			);
			const next = {};
			histories.forEach((h, i) => (next[watchlist[i].product.id] = h.history));
			priceHistories = next;
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function search() {
		if (!searchQuery.trim()) return;
		searching = true;
		try {
			searchResults = await priceSearch(searchQuery);
		} catch (e) {
			toast.error(e.message);
		} finally {
			searching = false;
		}
	}

	async function addToWatchlist(product) {
		await addWatchlist(product.game_id, targetPrice ? parseFloat(targetPrice) : null);
		toast.success(`Watching ${product.title}`);
		searchQuery = '';
		searchResults = [];
		targetPrice = '';
		await Promise.all([load(), watchStore.load()]);
	}

	let _scrollTarget = $state(0);

	beforeNavigate(() => {
		sessionStorage.setItem('watchlist_scroll', String(window.scrollY));
	});

	afterNavigate(({ type }) => {
		if (type === 'popstate') {
			_scrollTarget = Number(sessionStorage.getItem('watchlist_scroll') || '0');
			sessionStorage.removeItem('watchlist_scroll');
		}
	});

	$effect(() => {
		if (_scrollTarget && !loading) {
			const t = _scrollTarget;
			_scrollTarget = 0;
			tick().then(() => window.scrollTo({ top: t, behavior: 'instant' }));
		}
	});

	onMount(load);
</script>

<div class="space-y-6">
	<div class="flex items-end justify-between gap-4">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<Heart class="size-6 text-primary" /> Watchlist
			</h1>
			<p class="text-sm text-muted-foreground">
				{watched.length} game{watched.length === 1 ? '' : 's'} tracked
			</p>
		</div>
		{#if watched.length > 0}
			<select
				bind:value={sortBy}
				class="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm transition-colors hover:bg-muted/50"
			>
				{#each sortOptions as o}<option value={o.v}>{o.l}</option>{/each}
			</select>
		{/if}
	</div>

	<!-- Add to watchlist -->
	<Card.Root>
		<Card.Content class="space-y-3 p-4">
			<div class="flex flex-col gap-2 sm:flex-row">
				<div class="relative flex-1">
					<Search
						class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
					/>
					<Input
						bind:value={searchQuery}
						placeholder="Search a game to watch…"
						class="pl-9"
						onkeydown={(e) => e.key === 'Enter' && search()}
					/>
				</div>
				<Input bind:value={targetPrice} placeholder="Target ₹" class="sm:w-32" type="number" />
				<Button onclick={search} disabled={searching}>
					{searching ? 'Searching…' : 'Search'}
				</Button>
			</div>

			{#if searchResults.length > 0}
				<div class="max-h-72 divide-y overflow-y-auto rounded-lg border" transition:fly={{ y: -8 }}>
					{#each searchResults as r}
						<div
							class="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-muted/50"
						>
							<div class="min-w-0">
								<div class="truncate font-medium">{r.product.title}</div>
								<div class="text-xs text-muted-foreground">{r.product.store_id}</div>
							</div>
							<div class="flex shrink-0 items-center gap-3">
								{#if r.latest_price}
									<PriceTag price={r.latest_price.price} size="sm" />
									<StockBadge available={r.latest_price.available} size="sm" />
								{/if}
								<Button size="sm" onclick={() => addToWatchlist(r.product)}>
									<Plus class="size-3.5" /> Watch
								</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Grid -->
	{#if loading}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each Array(8) as _}
				<div class="space-y-2 rounded-xl border p-3">
					<Skeleton class="aspect-[4/3] w-full" />
					<Skeleton class="h-4 w-3/4" />
					<Skeleton class="h-4 w-1/2" />
				</div>
			{/each}
		</div>
	{:else if error}
		<p class="text-destructive">Error: {error}</p>
	{:else if watched.length === 0}
		<div
			class="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-16 text-center"
		>
			<Heart class="size-10 text-muted-foreground/40" />
			<div>
				<p class="font-medium">Your watchlist is empty</p>
				<p class="text-sm text-muted-foreground">
					Search above or browse to start tracking prices.
				</p>
			</div>
			<Button href="/browse" variant="outline">Browse games</Button>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each sortedWatchlist as item (item.watchlist.id)}
				<div animate:flip={{ duration: 250 }} in:fly={{ y: 12, duration: 200 }}>
					<ProductCard {item} history={priceHistories[item.product.id] ?? []} />
				</div>
			{/each}
		</div>
	{/if}
</div>
