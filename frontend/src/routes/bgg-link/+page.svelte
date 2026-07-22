<script>
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { linkBgg, bggUnlinked } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import InfiniteScroll from '$lib/components/InfiniteScroll.svelte';
	import { Link2 } from '@lucide/svelte';

	let products = $state([]);
	let total = $state(0);
	let page = $state(1);
	let loading = $state(false);
	let loadingMore = $state(false);
	let loadError = $state('');

	/** @type {Record<number, {urlRaw:string, expanded:boolean}>} */
	let rowState = $state({});

	onMount(() => load(true));

	async function load(reset = true) {
		if (reset) {
			loading = true;
			loadError = '';
			page = 1;
		} else {
			loadingMore = true;
		}
		try {
			const data = await bggUnlinked(page);
			products = reset ? data.products : [...products, ...data.products];
			total = data.total;
		} catch (e) {
			loadError = e.message;
			toast.error('Load failed: ' + e.message);
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMore() {
		page += 1;
		await load(false);
	}

	function row(id) {
		if (!rowState[id]) rowState[id] = { urlRaw: '', expanded: false };
		return rowState[id];
	}

	function toggle(productId) {
		const r = row(productId);
		r.expanded = !r.expanded;
	}

	function onPaste(productId, val) {
		const m = val.match(/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i);
		if (m) link(productId, Number(m[1]), val);
	}

	async function link(productId, bggId, bggName) {
		try {
			await linkBgg(bggId, productId);
			toast.success(`Linked "${bggName}"`);
			remove(productId);
		} catch (e) {
			toast.error('Link failed: ' + e.message);
		}
	}

	function remove(productId) {
		products = products.filter((p) => p.id !== productId);
		total = Math.max(0, total - 1);
		delete rowState[productId];
	}
</script>

<div class="space-y-5">
	<div class="flex items-center justify-between gap-3">
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<Link2 class="size-6 text-primary" /> BGG Link Manager
		</h1>
		{#if !loading}
			<span class="text-sm text-muted-foreground">{total} unlinked</span>
		{/if}
	</div>

	<p class="text-sm text-muted-foreground">
		Search BoardGameGeek for each product and confirm the match. Rate-limited — searches may take a
		moment.
	</p>

	{#if loading}
		<div class="space-y-2">
			{#each Array(8) as _}
				<div class="h-14 animate-pulse rounded-xl border bg-muted"></div>
			{/each}
		</div>
	{:else if loadError}
		<div
			class="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
		>
			Failed to load: {loadError}
			<button onclick={() => load(true)} class="ml-3 underline">Retry</button>
		</div>
	{:else if products.length === 0}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<Link2 class="size-10 text-muted-foreground/40" />
			<p class="font-medium">All games linked!</p>
			<p class="text-sm text-muted-foreground">No unlinked products remaining.</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each products as product (product.id)}
				{@const r = row(product.id)}
				<div
					class="overflow-hidden rounded-xl border bg-card transition-shadow"
					transition:fly={{ y: 4, duration: 180 }}
				>
					<!-- Row header -->
					<div class="flex items-center gap-3 p-3">
						{#if product.image_url}
							<img src={product.image_url} alt="" class="size-10 shrink-0 rounded object-cover" />
						{:else}
							<div
								class="grid size-10 shrink-0 place-items-center rounded bg-muted text-lg text-muted-foreground"
							>
								?
							</div>
						{/if}
						<span class="line-clamp-1 flex-1 text-sm font-medium">{product.title}</span>
						{#if product.watched}
							<span class="shrink-0 rounded-full bg-rose-500/15 px-2 py-0.5 text-xs text-rose-500"
								>watchlist</span
							>
						{/if}
						<Button
							size="sm"
							variant="outline"
							onclick={() =>
								window.open(
									`https://www.google.com/search?q=${encodeURIComponent('BGG ' + product.title)}`,
									'_blank'
								)}
						>
							Google ↗
						</Button>
						<Button
							size="sm"
							variant={r.expanded ? 'default' : 'outline'}
							onclick={() => toggle(product.id)}
						>
							{r.expanded ? 'Close' : 'Paste URL'}
						</Button>
						<Button size="sm" variant="ghost" onclick={() => remove(product.id)}>Skip</Button>
					</div>

					<!-- Paste URL panel -->
					{#if r.expanded}
						<div class="border-t px-3 pt-2 pb-3" transition:fly={{ y: -4, duration: 150 }}>
							<Input
								bind:value={r.urlRaw}
								placeholder="Paste BGG URL here…"
								class="text-sm"
								oninput={() => onPaste(product.id, r.urlRaw)}
							/>
							<p class="mt-1 text-xs text-muted-foreground">
								Google → open BGG page → copy URL → paste above. Links automatically.
							</p>
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<InfiniteScroll
			hasMore={products.length < total}
			loading={loadingMore}
			onload={loadMore}
			remaining={total - products.length}
		/>
	{/if}
</div>
