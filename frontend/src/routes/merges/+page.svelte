<script>
	import { onMount } from 'svelte';
	import { beforeNavigate } from '$app/navigation';
	import { fly } from 'svelte/transition';
	import { mergeQueue, decideMerges, fetchProductImage } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import { inr } from '$lib/gamePricing.js';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import { shortcuts, MERGE_SHORTCUTS } from '$lib/shortcuts.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import ProductImage from '$lib/components/ProductImage.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Merge, Check, X, ChevronRight, Undo2, Zap, ExternalLink } from '@lucide/svelte';

	const PAGE = 60;
	// Refill before the queue runs dry, so the reviewer never waits on a fetch.
	const REFILL_AT = 6;
	// Decisions are buffered, so a fast run costs one request instead of ten.
	const FLUSH_IDLE_MS = 800;
	const FLUSH_AT = 10;
	// Pairs to fetch images for ahead of the one on screen. Deciding is meant to
	// be held-down-key fast, and an image that arrives after the click is a stall.
	const PRELOAD_AHEAD = 4;

	let queue = $state([]);
	let index = $state(0);
	let total = $state(0);
	let loading = $state(true);
	let refilling = $state(false);
	let bulkThreshold = $state(150);

	/** Decisions taken but not yet sent. @type {Array<{pair:number[], kind:string}>} */
	let pending = $state([]);
	/** Everything decided this session, newest last — the undo stack. */
	let history = $state([]);
	let flushTimer = 0;
	let flushing = $state(false);

	const current = $derived(queue[index] ?? null);
	const upNext = $derived(queue.slice(index + 1, index + 4));
	const left = $derived(queue.length - index);
	const decidedCount = $derived(history.filter((h) => h.kind !== 'skip').length);
	const bulkTargets = $derived(
		queue.slice(index).filter((item) => item.score >= bulkThreshold).length
	);

	function pairOf(item) {
		return [item.left.product.id, item.right.product.id];
	}

	function priceOf(card) {
		return card.compare?.cheapest?.price ?? card.latest_price?.price ?? null;
	}

	/** product id -> image url, including ones resolved on demand. */
	let images = $state(new Map());
	const warmed = new Set();

	function srcFor(card) {
		return card.bgg?.thumbnail || card.product.image_url || images.get(card.product.id) || '';
	}

	/** Put a card's image in the browser cache before the card is shown. */
	async function warmCard(card) {
		const id = card.product.id;
		if (warmed.has(id)) return;
		warmed.add(id);
		let url = card.bgg?.thumbnail || card.product.image_url || '';
		if (!url) {
			try {
				url = (await fetchProductImage(id))?.image_url || '';
			} catch {
				return;
			}
			if (!url) return;
			images = new Map(images).set(id, url);
		}
		new Image().src = url;
	}

	function warmAhead() {
		for (const item of queue.slice(index, index + 1 + PRELOAD_AHEAD)) {
			warmCard(item.left);
			warmCard(item.right);
		}
	}

	async function load(reset = true) {
		if (reset) loading = true;
		else refilling = true;
		try {
			const res = await mergeQueue(PAGE);
			total = res.total ?? 0;
			// A pair already decided locally may still be in the server's answer
			// until the buffer is flushed.
			const seen = new Set(history.map((h) => h.pair.join(':')));
			const fresh = (res.items ?? []).filter((i) => !seen.has(pairOf(i).join(':')));
			queue = reset ? fresh : [...queue.slice(0, index), ...fresh];
			if (reset) index = 0;
		} catch (e) {
			toast.error(e.message);
		} finally {
			loading = false;
			refilling = false;
		}
	}

	function schedule() {
		clearTimeout(flushTimer);
		if (pending.length >= FLUSH_AT) {
			flush();
			return;
		}
		flushTimer = setTimeout(flush, FLUSH_IDLE_MS);
	}

	async function flush() {
		clearTimeout(flushTimer);
		if (!pending.length || flushing) return;
		const batch = pending;
		pending = [];
		flushing = true;
		try {
			await decideMerges(
				batch.filter((d) => d.kind === 'merge').map((d) => d.pair),
				batch.filter((d) => d.kind === 'reject').map((d) => d.pair)
			);
		} catch (e) {
			pending = [...batch, ...pending];
			toast.error(`Could not save ${batch.length} decision(s): ${e.message}`);
		} finally {
			flushing = false;
		}
	}

	/** @param {'merge'|'reject'|'skip'} kind */
	function decide(kind) {
		if (!current) return;
		const entry = { pair: pairOf(current), kind };
		history = [...history, entry];
		if (kind !== 'skip') {
			pending = [...pending, entry];
			schedule();
		}
		index += 1;
		if (left <= REFILL_AT && !refilling) load(false);
	}

	function undo() {
		const last = history[history.length - 1];
		if (!last) return;
		history = history.slice(0, -1);
		index = Math.max(0, index - 1);
		const at = pending.findIndex((p) => p.pair.join(':') === last.pair.join(':'));
		if (at !== -1) {
			pending = pending.filter((_, i) => i !== at);
			return;
		}
		if (last.kind !== 'skip') {
			toast.info('That one was already saved — undo it from the game page.');
		}
	}

	async function mergeAllAbove() {
		const targets = queue.slice(index).filter((item) => item.score >= bulkThreshold);
		if (!targets.length) return;
		if (!confirm(`Merge ${targets.length} pair(s) scoring ${bulkThreshold} or better?`)) return;
		const entries = targets.map((item) => ({ pair: pairOf(item), kind: 'merge' }));
		history = [...history, ...entries];
		pending = [...pending, ...entries];
		const skipped = new Set(entries.map((e) => e.pair.join(':')));
		queue = [
			...queue.slice(0, index),
			...queue.slice(index).filter((i) => !skipped.has(pairOf(i).join(':')))
		];
		await flush();
		toast.success(`Merged ${entries.length}`);
		await load(false);
	}

	$effect(() => {
		void queue;
		void index;
		warmAhead();
	});

	$effect(() =>
		shortcuts.register(MERGE_SHORTCUTS, {
			y: () => decide('merge'),
			n: () => decide('reject'),
			s: () => decide('skip'),
			z: undo
		})
	);

	beforeNavigate(flush);

	onMount(() => {
		load();
		const onHide = () => document.visibilityState === 'hidden' && flush();
		document.addEventListener('visibilitychange', onHide);
		return () => {
			document.removeEventListener('visibilitychange', onHide);
			flush();
		};
	});
</script>

<svelte:window onbeforeunload={flush} />

{#snippet side(card, align)}
	{@const store = card.product.store_id}
	{@const color = storeColors.of(store)}
	<div
		class="flex min-w-0 flex-1 flex-col gap-3 rounded-xl border p-4 {align === 'right'
			? 'sm:items-end sm:text-right'
			: ''}"
		style="border-color:{tint(color, 0.45)}; background:{tint(color, 0.05)}"
	>
		<div class="flex items-center gap-1.5 text-xs font-medium">
			<span class="size-2.5 rounded-full" style="background:{color}" aria-hidden="true"></span>
			{storeColors.name(store)}
		</div>
		<ProductImage
			src={srcFor(card)}
			productId={card.product.id}
			alt={card.game.title}
			eager
			class="h-28 w-full rounded-lg object-contain"
		/>
		<div class="min-w-0">
			<a href="/games/{card.game.id}" class="line-clamp-2 font-medium hover:underline">
				{card.game.title}
			</a>
			<p class="line-clamp-1 text-xs text-muted-foreground" title={card.product.title}>
				listed as “{card.product.title}”
			</p>
		</div>
		<div class="flex items-center gap-2">
			<span class="text-lg font-bold tabular-nums">{inr(priceOf(card))}</span>
			{#if card.product.url}
				<a
					href={card.product.url}
					target="_blank"
					class="text-muted-foreground hover:text-foreground"
					aria-label="Open at {store}"
				>
					<ExternalLink class="size-3.5" />
				</a>
			{/if}
		</div>
	</div>
{/snippet}

<div class="space-y-5">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<Merge class="size-6 text-primary" /> Merges
			</h1>
			<p class="text-sm text-muted-foreground">
				Best matches first. One listing per shop, so each pair is asked once.
			</p>
		</div>
		<div class="text-right text-sm text-muted-foreground">
			<div><span class="font-semibold text-foreground">{decidedCount}</span> decided</div>
			<div>{total} candidate{total === 1 ? '' : 's'} found</div>
		</div>
	</div>

	{#if loading}
		<Card.Root
			><Card.Content class="space-y-4 p-6">
				<Skeleton class="h-40 w-full" />
				<Skeleton class="h-10 w-2/3" />
			</Card.Content></Card.Root
		>
	{:else if !current}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<Check class="size-10 text-muted-foreground/40" />
			<p class="font-medium">Nothing left to review</p>
			<p class="text-sm text-muted-foreground">
				Every cross-store match above the confidence floor has been decided.
			</p>
			<Button variant="outline" size="sm" class="mt-2" onclick={() => load()}>Check again</Button>
		</div>
	{:else}
		<Card.Root>
			<Card.Content class="space-y-4 p-4 sm:p-6">
				{#key current.left.product.id}
					<div
						class="flex flex-col items-stretch gap-3 sm:flex-row"
						in:fly={{ y: 8, duration: 140 }}
					>
						{@render side(current.left, 'left')}
						<div class="flex shrink-0 flex-col items-center justify-center gap-1 px-2">
							<span class="text-xs text-muted-foreground">match</span>
							<span class="text-2xl font-bold tabular-nums">{Math.round(current.score)}</span>
						</div>
						{@render side(current.right, 'right')}
					</div>
				{/key}

				<div class="flex flex-wrap gap-2">
					<Button class="flex-1 gap-1.5" onclick={() => decide('merge')}>
						<Check class="size-4" /> Same game
						<kbd class="rounded border border-b-2 bg-background/20 px-1 font-mono text-[10px]"
							>Y</kbd
						>
					</Button>
					<Button variant="outline" class="flex-1 gap-1.5" onclick={() => decide('reject')}>
						<X class="size-4" /> Not the same
						<kbd class="rounded border border-b-2 bg-muted px-1 font-mono text-[10px]">N</kbd>
					</Button>
					<Button variant="ghost" class="gap-1.5" onclick={() => decide('skip')}>
						<ChevronRight class="size-4" /> Skip
						<kbd class="rounded border border-b-2 bg-muted px-1 font-mono text-[10px]">S</kbd>
					</Button>
					<Button variant="ghost" class="gap-1.5" disabled={!history.length} onclick={undo}>
						<Undo2 class="size-4" />
						<kbd class="rounded border border-b-2 bg-muted px-1 font-mono text-[10px]">Z</kbd>
					</Button>
				</div>

				{#if pending.length}
					<p class="text-xs text-muted-foreground">
						{pending.length} decision{pending.length === 1 ? '' : 's'} saving…
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Content class="flex flex-wrap items-center gap-3 p-4">
				<Zap class="size-4 text-primary" />
				<span class="text-sm">Merge everything scoring at least</span>
				<input
					type="number"
					bind:value={bulkThreshold}
					min="78"
					max="200"
					step="1"
					class="h-8 w-20 rounded-lg border bg-background px-2 text-sm tabular-nums"
				/>
				<Button size="sm" disabled={!bulkTargets || flushing} onclick={mergeAllAbove}>
					Merge {bulkTargets} pair{bulkTargets === 1 ? '' : 's'}
				</Button>
				<span class="text-xs text-muted-foreground">
					200 means the names match exactly once shop wording is stripped.
				</span>
			</Card.Content>
		</Card.Root>

		{#if upNext.length}
			<div>
				<p class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
					Up next
				</p>
				<div class="grid gap-2 sm:grid-cols-3">
					{#each upNext as item (item.left.product.id)}
						<div class="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs">
							<span class="font-semibold tabular-nums">{Math.round(item.score)}</span>
							<span class="line-clamp-1 flex-1 text-muted-foreground">{item.left.game.title}</span>
							<span
								class="size-2 shrink-0 rounded-full"
								style="background:{storeColors.of(item.left.product.store_id)}"
								aria-hidden="true"
							></span>
							<span
								class="size-2 shrink-0 rounded-full"
								style="background:{storeColors.of(item.right.product.store_id)}"
								aria-hidden="true"
							></span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>
