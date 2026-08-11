<script>
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { beforeNavigate } from '$app/navigation';
	import { fly } from 'svelte/transition';
	import { mergeQueue, decideMerges, rejectedQueue, fetchProductImage } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import { inr } from '$lib/gamePricing.js';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import { shortcuts, MERGE_SHORTCUTS } from '$lib/shortcuts.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import ProductImage from '$lib/components/ProductImage.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import {
		Merge,
		Check,
		X,
		ChevronRight,
		Undo2,
		Zap,
		ExternalLink,
		List,
		RotateCcw,
		Ban
	} from '@lucide/svelte';

	const PAGE = 60;
	// Refill before the queue runs dry, so the reviewer never waits on a fetch.
	const REFILL_AT = 6;
	// Decisions are buffered, so a fast run costs one request instead of ten.
	const FLUSH_IDLE_MS = 800;
	const FLUSH_AT = 10;
	// Pairs to fetch images for ahead of the one on screen. Deciding is meant to
	// be held-down-key fast, and an image that arrives after the click is a stall.
	const PRELOAD_AHEAD = 4;
	// Skips outlive the tab: "later" is only useful if it survives a reload.
	const SKIP_KEY = 'gd-merge-skipped';
	// Unsent decisions are mirrored here, so a decision is never lost to a
	// reload, a crash or a beacon the browser refused.
	const PENDING_KEY = 'gd-merge-pending';

	const MODES = [
		{ id: 'review', label: 'Review', icon: Merge },
		{ id: 'list', label: 'All above score', icon: List },
		{ id: 'skipped', label: 'Skipped', icon: ChevronRight },
		{ id: 'rejected', label: 'Rejected', icon: Ban }
	];

	let mode = $state('review');
	let queue = $state([]);
	let index = $state(0);
	let total = $state(0);
	let loading = $state(true);
	let refilling = $state(false);
	let bulkThreshold = $state(150);

	/** Pairs put off for later, kept out of the review queue. */
	let skipped = $state([]);
	let skippedKeys = $state(new Set());

	let rejected = $state([]);
	let rejectedTotal = $state(0);
	let rejectedLoading = $state(false);
	let rejectedFloor = $state(120);

	/** Decisions taken but not yet sent. Seeded from a previous visit's leftovers.
	 * @type {Array<{pair:number[], kind:string}>} */
	let pending = $state(browser ? readPending() : []);
	/** Everything decided this session, newest last — the undo stack. */
	let history = $state([]);
	let flushTimer = 0;
	let flushing = $state(false);

	const current = $derived(queue[index] ?? null);
	const upNext = $derived(queue.slice(index + 1, index + 4));
	const left = $derived(queue.length - index);
	const decidedCount = $derived(history.filter((h) => h.kind !== 'skip').length);
	const aboveThreshold = $derived(queue.slice(index).filter((i) => i.score >= bulkThreshold));

	function pairOf(item) {
		return [item.left.product.id, item.right.product.id];
	}

	function keyOf(item) {
		return pairOf(item).join(':');
	}

	function priceOf(card) {
		return card.compare?.cheapest?.price ?? card.latest_price?.price ?? null;
	}

	// ---------------------------------------------------------------------------
	// Images
	// ---------------------------------------------------------------------------

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

	// ---------------------------------------------------------------------------
	// Loading
	// ---------------------------------------------------------------------------

	function readSkips() {
		try {
			return new Set(JSON.parse(localStorage.getItem(SKIP_KEY) ?? '[]'));
		} catch {
			return new Set();
		}
	}

	function readPending() {
		try {
			return JSON.parse(localStorage.getItem(PENDING_KEY) ?? '[]');
		} catch {
			return [];
		}
	}

	function writeSkips(keys) {
		skippedKeys = keys;
		try {
			localStorage.setItem(SKIP_KEY, JSON.stringify([...keys]));
		} catch {
			// Private mode or a full quota: skips just won't outlive the tab.
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
			const seen = new Set(history.filter((h) => h.kind !== 'skip').map((h) => h.pair.join(':')));
			const fresh = (res.items ?? []).filter((i) => !seen.has(keyOf(i)));
			skipped = fresh.filter((i) => skippedKeys.has(keyOf(i)));
			const open = fresh.filter((i) => !skippedKeys.has(keyOf(i)));
			queue = reset ? open : [...queue.slice(0, index), ...open];
			if (reset) index = 0;
		} catch (e) {
			toast.error(e.message);
		} finally {
			loading = false;
			refilling = false;
		}
	}

	async function loadRejected() {
		rejectedLoading = true;
		try {
			const res = await rejectedQueue(PAGE, rejectedFloor);
			rejected = res.items ?? [];
			rejectedTotal = res.total ?? 0;
		} catch (e) {
			toast.error(e.message);
		} finally {
			rejectedLoading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Decisions
	// ---------------------------------------------------------------------------

	function schedule() {
		clearTimeout(flushTimer);
		if (pending.length >= FLUSH_AT) {
			flush();
			return;
		}
		flushTimer = setTimeout(flush, FLUSH_IDLE_MS);
	}

	function batchBody(batch) {
		return {
			merges: batch.filter((d) => d.kind === 'merge').map((d) => d.pair),
			rejects: batch.filter((d) => d.kind === 'reject').map((d) => d.pair),
			unrejects: batch.filter((d) => d.kind === 'unreject').map((d) => d.pair)
		};
	}

	async function flush() {
		clearTimeout(flushTimer);
		if (!pending.length || flushing) return;
		const batch = pending;
		pending = [];
		flushing = true;
		const body = batchBody(batch);
		try {
			await decideMerges(body.merges, body.rejects, body.unrejects);
		} catch (e) {
			pending = [...batch, ...pending];
			toast.error(`Could not save ${batch.length} decision(s): ${e.message}`);
		} finally {
			flushing = false;
		}
	}

	/** A reload cancels in-flight fetches, so leaving the page posts by beacon. */
	function flushOnUnload() {
		if (!pending.length) return;
		const blob = new Blob([JSON.stringify(batchBody(pending))], { type: 'application/json' });
		if (navigator.sendBeacon?.('/api/games/suggestions/decide', blob)) {
			clearTimeout(flushTimer);
			pending = [];
			return;
		}
		flush();
	}

	/** Queue a decision for sending and drop the pair from every view. */
	function apply(item, kind) {
		const key = keyOf(item);
		// The item rides along in history so undo can put the pair back.
		history = [...history, { pair: pairOf(item), kind, item }];
		pending = [...pending, { pair: pairOf(item), kind }];
		queue = queue.filter((i) => keyOf(i) !== key);
		skipped = skipped.filter((i) => keyOf(i) !== key);
		rejected = rejected.filter((i) => keyOf(i) !== key);
		if (skippedKeys.has(key)) {
			const next = new Set(skippedKeys);
			next.delete(key);
			writeSkips(next);
		}
		schedule();
	}

	/** @param {'merge'|'reject'|'skip'} kind */
	function decide(kind) {
		if (mode !== 'review' || !current) return;
		if (kind === 'skip') {
			const item = current;
			history = [...history, { pair: pairOf(item), kind, item }];
			skipped = [...skipped, item];
			writeSkips(new Set(skippedKeys).add(keyOf(item)));
			queue = queue.filter((i) => keyOf(i) !== keyOf(item));
		} else {
			apply(current, kind);
		}
		if (left <= REFILL_AT && !refilling) load(false);
	}

	/** Take back the last decision, as long as it has not been sent yet. */
	function undo() {
		const last = history[history.length - 1];
		if (!last) return;
		const key = last.pair.join(':');
		const at = pending.findIndex((p) => p.pair.join(':') === key);
		if (at === -1 && last.kind !== 'skip') {
			toast.info('That one was already saved — undo it from the game page.');
			return;
		}
		history = history.slice(0, -1);
		if (at !== -1) pending = pending.filter((_, i) => i !== at);
		if (last.kind === 'skip') {
			const next = new Set(skippedKeys);
			next.delete(key);
			writeSkips(next);
			skipped = skipped.filter((i) => keyOf(i) !== key);
		}
		queue = [...queue.slice(0, index), last.item, ...queue.slice(index)];
	}

	/** Put a skipped pair back at the front of the review queue. */
	function unskip(item) {
		const key = keyOf(item);
		const next = new Set(skippedKeys);
		next.delete(key);
		writeSkips(next);
		skipped = skipped.filter((i) => keyOf(i) !== key);
		queue = [...queue.slice(0, index), item, ...queue.slice(index)];
		mode = 'review';
	}

	function clearSkips() {
		queue = [...queue.slice(0, index), ...skipped, ...queue.slice(index)];
		skipped = [];
		writeSkips(new Set());
		mode = 'review';
	}

	async function mergeAllAbove() {
		const targets = aboveThreshold;
		if (!targets.length) return;
		if (!confirm(`Merge ${targets.length} pair(s) scoring ${bulkThreshold} or better?`)) return;
		for (const item of targets) apply(item, 'merge');
		await flush();
		toast.success(`Merged ${targets.length}`);
		await load(false);
	}

	$effect(() => {
		void queue;
		void index;
		warmAhead();
	});

	$effect(() => {
		try {
			localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
		} catch {
			// Nothing to fall back to; the flush paths still cover the normal case.
		}
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
		skippedKeys = readSkips();
		// Leftovers from a previous visit go out before the first read, so the
		// queue never re-asks something already answered.
		if (pending.length) flush().then(() => load());
		else load();
		const onHide = () => document.visibilityState === 'hidden' && flushOnUnload();
		document.addEventListener('visibilitychange', onHide);
		window.addEventListener('pagehide', flushOnUnload);
		return () => {
			document.removeEventListener('visibilitychange', onHide);
			window.removeEventListener('pagehide', flushOnUnload);
			flush();
		};
	});
</script>

<svelte:window onbeforeunload={flushOnUnload} />

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

{#snippet rowSide(card)}
	<div class="flex min-w-0 flex-1 items-center gap-2">
		<ProductImage
			src={srcFor(card)}
			productId={card.product.id}
			alt=""
			class="size-14 shrink-0 rounded-md bg-background"
		/>
		<span
			class="size-2 shrink-0 rounded-full"
			style="background:{storeColors.of(card.product.store_id)}"
			aria-hidden="true"
		></span>
		<a href="/games/{card.game.id}" class="line-clamp-2 text-sm hover:underline">
			{card.game.title}
		</a>
	</div>
{/snippet}

<!-- Both sides at once: the point of the preview is telling two boxes apart,
     which one enlarged image can't do. Floating and click-through, so the row
     heights — and so the buttons under the pointer — never move. -->
{#snippet rowPreview(item)}
	<div
		class="pointer-events-none absolute bottom-full left-14 z-40 mb-1 hidden gap-3 rounded-xl border bg-popover p-3 shadow-2xl group-hover/row:flex"
	>
		{#each [item.left, item.right] as card (card.product.id)}
			<div class="w-52">
				<ProductImage
					src={srcFor(card)}
					productId={card.product.id}
					alt={card.game.title}
					eager
					class="h-52 w-52 rounded-lg"
				/>
				<p class="mt-1.5 flex items-center gap-1.5 text-xs">
					<span
						class="size-2 shrink-0 rounded-full"
						style="background:{storeColors.of(card.product.store_id)}"
						aria-hidden="true"
					></span>
					<span class="line-clamp-2">{card.product.title}</span>
				</p>
			</div>
		{/each}
	</div>
{/snippet}

<!-- Fixed height: a decided row leaves, the next slides into the same place, and
     the pointer is already on its button. -->
{#snippet row(item, actions)}
	<div class="group/row relative flex h-20 items-center gap-3 rounded-lg border px-2.5">
		{@render rowPreview(item)}
		<span class="w-8 shrink-0 text-center font-semibold tabular-nums">
			{Math.round(item.score)}
		</span>
		{@render rowSide(item.left)}
		{@render rowSide(item.right)}
		<div class="flex shrink-0 gap-1.5">
			{@render actions(item)}
		</div>
	</div>
{/snippet}

{#snippet queueActions(item)}
	<Button size="sm" class="h-7 text-xs" onclick={() => apply(item, 'merge')}>
		<Check class="size-3.5" /> Merge
	</Button>
	<Button size="sm" variant="ghost" class="h-7 text-xs" onclick={() => apply(item, 'reject')}>
		<X class="size-3.5" /> No
	</Button>
{/snippet}

{#snippet skippedActions(item)}
	<Button size="sm" class="h-7 text-xs" onclick={() => apply(item, 'merge')}>
		<Check class="size-3.5" /> Merge
	</Button>
	<Button size="sm" variant="ghost" class="h-7 text-xs" onclick={() => apply(item, 'reject')}>
		<X class="size-3.5" /> No
	</Button>
	<Button size="sm" variant="outline" class="h-7 text-xs" onclick={() => unskip(item)}>
		<RotateCcw class="size-3.5" /> Review
	</Button>
{/snippet}

{#snippet rejectedActions(item)}
	<Button size="sm" class="h-7 text-xs" onclick={() => apply(item, 'merge')}>
		<Check class="size-3.5" /> Same after all
	</Button>
	<Button
		size="sm"
		variant="outline"
		class="h-7 text-xs"
		onclick={() => apply(item, 'unreject')}
		title="Put it back in the review queue"
	>
		<RotateCcw class="size-3.5" /> Ask again
	</Button>
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

	<div class="flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1">
		{#each MODES as m (m.id)}
			{@const Icon = m.icon}
			<button
				onclick={() => {
					mode = m.id;
					if (m.id === 'rejected' && !rejected.length) loadRejected();
				}}
				class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {mode ===
				m.id
					? 'bg-background text-foreground shadow-sm'
					: 'text-muted-foreground hover:text-foreground'}"
				aria-current={mode === m.id}
			>
				<Icon class="size-3.5" />
				{m.label}
				{#if m.id === 'skipped' && skipped.length}
					<span class="rounded-full bg-primary/15 px-1.5 text-[0.65rem] text-primary">
						{skipped.length}
					</span>
				{/if}
			</button>
		{/each}
	</div>

	{#if loading}
		<Card.Root
			><Card.Content class="space-y-4 p-6">
				<Skeleton class="h-40 w-full" />
				<Skeleton class="h-10 w-2/3" />
			</Card.Content></Card.Root
		>
	{:else if mode === 'review'}
		{#if !current}
			<div
				class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center"
			>
				<Check class="size-10 text-muted-foreground/40" />
				<p class="font-medium">Nothing left to review</p>
				<p class="text-sm text-muted-foreground">
					{skipped.length
						? `${skipped.length} skipped pair(s) are waiting under Skipped.`
						: 'Every cross-store match above the confidence floor has been decided.'}
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

			{#if upNext.length}
				<div>
					<p class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
						Up next
					</p>
					<div class="grid gap-2 sm:grid-cols-3">
						{#each upNext as item (keyOf(item))}
							<div class="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs">
								<span class="font-semibold tabular-nums">{Math.round(item.score)}</span>
								<span class="line-clamp-1 flex-1 text-muted-foreground">{item.left.game.title}</span
								>
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
	{:else if mode === 'list'}
		<Card.Root>
			<Card.Content class="flex flex-wrap items-center gap-3 p-4">
				<Zap class="size-4 text-primary" />
				<span class="text-sm">Show pairs scoring at least</span>
				<input
					type="number"
					bind:value={bulkThreshold}
					min="78"
					max="200"
					step="1"
					class="h-8 w-20 rounded-lg border bg-background px-2 text-sm tabular-nums"
				/>
				<Button size="sm" disabled={!aboveThreshold.length || flushing} onclick={mergeAllAbove}>
					Merge all {aboveThreshold.length}
				</Button>
				<span class="text-xs text-muted-foreground">
					200 means the names match exactly once shop wording is stripped.
				</span>
			</Card.Content>
		</Card.Root>

		{#if !aboveThreshold.length}
			<p class="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
				No pairs at {bulkThreshold} or above. Lower the score to see more.
			</p>
		{:else}
			<div class="space-y-2">
				{#each aboveThreshold as item (keyOf(item))}
					{@render row(item, queueActions)}
				{/each}
			</div>
		{/if}
	{:else if mode === 'skipped'}
		{#if !skipped.length}
			<p class="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
				Nothing skipped. Press S while reviewing to park a pair here.
			</p>
		{:else}
			<div class="flex justify-end">
				<Button variant="ghost" size="sm" onclick={clearSkips}>
					<RotateCcw class="size-3.5" /> Send all back to review
				</Button>
			</div>
			<div class="space-y-2">
				{#each skipped as item (keyOf(item))}
					{@render row(item, skippedActions)}
				{/each}
			</div>
		{/if}
	{:else}
		<Card.Root>
			<Card.Content class="flex flex-wrap items-center gap-3 p-4">
				<Ban class="size-4 text-muted-foreground" />
				<span class="text-sm">Rejected pairs scoring at least</span>
				<input
					type="number"
					bind:value={rejectedFloor}
					min="0"
					max="200"
					step="1"
					class="h-8 w-20 rounded-lg border bg-background px-2 text-sm tabular-nums"
				/>
				<Button size="sm" variant="outline" disabled={rejectedLoading} onclick={loadRejected}>
					{rejectedLoading ? 'Loading…' : 'Show'}
				</Button>
				<span class="text-xs text-muted-foreground">
					{rejectedTotal} rejected pair{rejectedTotal === 1 ? '' : 's'} at this score
				</span>
			</Card.Content>
		</Card.Root>

		{#if rejectedLoading}
			<Skeleton class="h-24 w-full" />
		{:else if !rejected.length}
			<p class="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
				No rejected pairs at {rejectedFloor} or above.
			</p>
		{:else}
			<div class="space-y-2">
				{#each rejected as item (keyOf(item))}
					{@render row(item, rejectedActions)}
				{/each}
			</div>
		{/if}
	{/if}
</div>
