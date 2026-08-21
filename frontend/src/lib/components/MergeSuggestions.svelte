<script>
	import { mergeSuggestions, mergeCandidates, mergeProducts, rejectMerge } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import ProductImage from './ProductImage.svelte';
	import Skeleton from './Skeleton.svelte';
	import { inr } from '$lib/priceFormat.svelte.js';
	import { Check, X, Link2, Search } from '@lucide/svelte';

	let { productId, onmerged = /** @type {((payload:any)=>void)|null} */ (null) } = $props();

	let items = $state([]);
	let loading = $state(true);
	let busy = $state(/** @type {Record<number, string>} */ ({}));

	// Manual search: the ranked list can miss a game whose shops named it
	// completely differently, so the user can go find it by name.
	let searchOpen = $state(false);
	let query = $state('');
	let results = $state([]);
	let searching = $state(false);
	let searched = $state(false);

	async function load() {
		if (productId == null) return;
		loading = true;
		try {
			items = (await mergeSuggestions(productId)).items ?? [];
		} catch {
			items = [];
		} finally {
			loading = false;
		}
	}

	async function runSearch() {
		if (!query.trim() || productId == null) return;
		searching = true;
		try {
			results = (await mergeCandidates(productId, query)).items ?? [];
			searched = true;
		} catch (e) {
			toast.error(e.message);
		} finally {
			searching = false;
		}
	}

	function drop(candidateId) {
		items = items.filter((i) => i.item.product.id !== candidateId);
		results = results.filter((i) => i.item.product.id !== candidateId);
	}

	async function confirm(candidateId) {
		busy = { ...busy, [candidateId]: 'merge' };
		try {
			const payload = await mergeProducts(productId, candidateId);
			drop(candidateId);
			toast.success('Merged — prices now compared side by side');
			onmerged?.(payload);
			// The rest of the list was answering "which game is this listing?",
			// which is now settled — re-ask for whatever still stands.
			results = [];
			await load();
		} catch (e) {
			toast.error(e.message);
		} finally {
			const { [candidateId]: _, ...rest } = busy;
			busy = rest;
		}
	}

	async function dismiss(candidateId) {
		busy = { ...busy, [candidateId]: 'reject' };
		try {
			await rejectMerge(productId, candidateId);
			drop(candidateId);
		} catch (e) {
			toast.error(e.message);
		} finally {
			const { [candidateId]: _, ...rest } = busy;
			busy = rest;
		}
	}

	$effect(() => {
		void productId;
		searchOpen = false;
		query = '';
		results = [];
		searched = false;
		load();
	});
</script>

{#snippet candidate(s, showScore)}
	{@const p = s.item.product}
	{@const price = s.item.compare?.cheapest?.price ?? s.item.latest_price?.price ?? null}
	<div class="flex gap-3 rounded-lg border p-2">
		<a href="/games/{s.item.game.id}" class="shrink-0">
			<ProductImage
				src={s.item.bgg?.thumbnail || p.image_url || ''}
				productId={p.id}
				alt={s.item.game.title}
				class="size-14 rounded-md"
			/>
		</a>
		<div class="min-w-0 flex-1">
			<a href="/games/{s.item.game.id}" class="line-clamp-2 text-sm leading-tight hover:underline">
				{s.item.game.title}
			</a>
			<div class="mt-1 flex flex-wrap items-center gap-1.5">
				<Badge variant="outline" class="text-[0.65rem]">{p.store_id}</Badge>
				<span class="text-xs font-semibold tabular-nums">{inr(price)}</span>
				{#if showScore}
					<span class="text-[0.65rem] text-muted-foreground" title="Name match score">
						{Math.round(s.score)} match
					</span>
				{/if}
				{#if s.rejected}
					<span class="text-[0.65rem] text-amber-600">previously rejected</span>
				{/if}
			</div>
			<div class="mt-2 flex gap-1.5">
				<Button
					size="sm"
					class="h-7 flex-1 text-xs"
					disabled={!!busy[p.id]}
					onclick={() => confirm(p.id)}
				>
					<Check class="size-3.5" /> Same game
				</Button>
				<Button
					size="sm"
					variant="ghost"
					class="h-7 text-xs"
					disabled={!!busy[p.id]}
					onclick={() => dismiss(p.id)}
				>
					<X class="size-3.5" /> No
				</Button>
			</div>
		</div>
	</div>
{/snippet}

<Card.Root>
	<Card.Header class="pb-3">
		<Card.Title class="flex items-center gap-2 text-base">
			<Link2 class="size-4" /> Same game elsewhere?
		</Card.Title>
		<Card.Description>Confirm to compare prices across stores.</Card.Description>
	</Card.Header>
	<Card.Content class="space-y-2">
		{#if loading}
			{#each [1, 2] as i}
				<div class="flex gap-3">
					<Skeleton class="size-14 rounded-md" />
					<div class="flex-1 space-y-2">
						<Skeleton class="h-4 w-3/4" />
						<Skeleton class="h-3 w-1/3" />
					</div>
				</div>
			{/each}
		{:else}
			{#each items as s (s.item.product.id)}
				{@render candidate(s, true)}
			{/each}

			{#if !items.length}
				<p class="text-sm text-muted-foreground">
					No close matches at other stores. Search by name if you know it is sold elsewhere.
				</p>
			{/if}

			<div class="border-t pt-2">
				{#if !searchOpen}
					<Button variant="ghost" size="sm" class="text-xs" onclick={() => (searchOpen = true)}>
						<Search class="size-3.5" /> Find it by name
					</Button>
				{:else}
					<div class="space-y-2">
						<div class="flex gap-1.5">
							<Input
								bind:value={query}
								placeholder="Search other stores…"
								class="h-8 text-sm"
								onkeydown={(e) => e.key === 'Enter' && runSearch()}
							/>
							<Button
								size="sm"
								variant="outline"
								class="h-8"
								disabled={searching || !query.trim()}
								onclick={runSearch}
							>
								<Search class="size-3.5 {searching ? 'animate-pulse' : ''}" />
							</Button>
						</div>
						{#each results as s (s.item.product.id)}
							{@render candidate(s, false)}
						{/each}
						{#if searched && !results.length && !searching}
							<p class="text-xs text-muted-foreground">
								Nothing found at other stores for “{query}”.
							</p>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</Card.Content>
</Card.Root>
