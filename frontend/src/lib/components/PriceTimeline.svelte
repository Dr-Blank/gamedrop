<script>
	import { ChevronDown, EyeOff, RotateCcw, Trash2 } from '@lucide/svelte';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { inrExact } from '$lib/priceFormat.svelte.js';
	import { fmtDateParts } from '$lib/dateFormat.svelte.js';

	let {
		events = /** @type {Array<any>} */ ([]),
		ignored = /** @type {Array<any>} */ ([]),
		multiStore = false,
		limit = 12,
		busy = /** @type {Set<number>} */ (new Set()),
		onignore = /** @type {((e: any) => void) | null} */ (null),
		onrestore = /** @type {((e: any) => void) | null} */ (null),
		ondelete = /** @type {((e: any) => void) | null} */ (null)
	} = $props();

	let showAll = $state(false);
	let open = $state(new Set());
	const shown = $derived(showAll ? events : events.slice(0, limit));

	/** @param {any} e */
	const key = (e) => `${e.product_id ?? e.store_id}-${e.at}`;

	/** @param {any} e */
	function toggle(e) {
		const next = new Set(open);
		if (next.has(key(e))) next.delete(key(e));
		else next.add(key(e));
		open = next;
	}

	/** @param {string} at */
	const when = (at) =>
		fmtDateParts(at, {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});

	/** @param {any} e */
	const pct = (e) =>
		e.prevPrice
			? `${e.price > e.prevPrice ? '+' : ''}${(((e.price - e.prevPrice) / e.prevPrice) * 100).toFixed(1)}%`
			: '';
</script>

{#snippet manualTag()}
	<span
		class="rounded bg-muted px-1.5 py-0.5 text-[0.65rem] font-medium tracking-wide text-muted-foreground uppercase"
	>
		Added by hand
	</span>
{/snippet}

{#snippet row(e, nested = false)}
	{@const color = storeColors.of(e.store_id)}
	<li class="group relative flex gap-3 py-2.5 {nested ? 'pl-6' : ''}">
		<span
			class="mt-1.5 size-2.5 shrink-0 rounded-full"
			style:background-color={e.available ? color : 'transparent'}
			style:box-shadow="inset 0 0 0 1.5px {color}"
		></span>
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
				{#if e.kind === 'drop' || e.kind === 'rise'}
					<span class="text-sm text-muted-foreground tabular-nums line-through">
						{inrExact(e.prevPrice)}
					</span>
					<span
						class="text-sm font-semibold tabular-nums {e.kind === 'drop'
							? 'text-green-600 dark:text-green-400'
							: 'text-rose-500'}"
					>
						{inrExact(e.price)}
					</span>
					<span
						class="text-xs tabular-nums {e.kind === 'drop'
							? 'text-green-600 dark:text-green-400'
							: 'text-rose-500'}"
					>
						{pct(e)}
					</span>
				{:else if e.kind === 'flaps'}
					<button
						onclick={() => toggle(e)}
						class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
					>
						<ChevronDown
							class="size-4 transition-transform {open.has(key(e)) ? 'rotate-180' : ''}"
						/>
						In and out of stock {e.count}×
					</button>
					<span class="text-sm tabular-nums">{inrExact(e.price)}</span>
				{:else}
					<span class="text-sm">
						{e.kind === 'listed'
							? 'First seen'
							: e.kind === 'oos'
								? 'Out of stock'
								: 'Back in stock'}
					</span>
					<span class="text-sm font-semibold tabular-nums">{inrExact(e.price)}</span>
				{/if}
				{#if multiStore}
					<span class="text-xs" style:color>{storeColors.name(e.store_id)}</span>
				{/if}
				{#if e.source === 'manual'}
					{@render manualTag()}
				{/if}
			</div>
			<div class="text-xs text-muted-foreground">
				{e.kind === 'flaps' ? `${when(e.since)} — ${when(e.at)}` : when(e.at)}
			</div>
			{#if e.kind === 'flaps' && open.has(key(e))}
				<ul class="mt-1 border-l pl-1">
					{#each e.events.slice().reverse() as child}
						{@render row(child, true)}
					{/each}
				</ul>
			{/if}
		</div>

		<!-- A wrong reading is dismissed here, never deleted: the shop did publish it. -->
		{#if e.kind !== 'flaps' && e.snapshot_id != null}
			<div
				class="flex shrink-0 items-start gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
			>
				{#if onignore}
					<button
						onclick={() => onignore(e)}
						disabled={busy.has(e.snapshot_id)}
						title="Ignore this reading"
						aria-label="Ignore this reading"
						class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
					>
						<EyeOff class="size-3.5" />
					</button>
				{/if}
				{#if ondelete && e.source === 'manual'}
					<button
						onclick={() => ondelete(e)}
						disabled={busy.has(e.snapshot_id)}
						title="Delete this hand-added reading"
						aria-label="Delete this hand-added reading"
						class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-rose-500 disabled:opacity-40"
					>
						<Trash2 class="size-3.5" />
					</button>
				{/if}
			</div>
		{/if}
	</li>
{/snippet}

{#if events.length}
	<ul class="divide-y">
		{#each shown as e (key(e))}
			{@render row(e)}
		{/each}
	</ul>
	{#if events.length > limit}
		<button
			onclick={() => (showAll = !showAll)}
			class="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
		>
			<ChevronDown class="size-4 transition-transform {showAll ? 'rotate-180' : ''}" />
			{showAll ? 'Show less' : `Show all ${events.length}`}
		</button>
	{/if}
{:else}
	<p class="text-sm text-muted-foreground">Nothing has changed yet — no price moves recorded.</p>
{/if}

{#if ignored.length}
	<div class="mt-4 rounded-lg border border-dashed p-3">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
			<EyeOff class="size-3.5" />
			Ignored — left out of the chart, stats and alerts
		</div>
		<ul class="space-y-1.5">
			{#each ignored as s (s.id)}
				<li class="flex items-center gap-2 text-sm">
					<span class="tabular-nums line-through opacity-60">{inrExact(s.price)}</span>
					<span class="text-xs text-muted-foreground">{when(s.recorded_at)}</span>
					{#if multiStore}
						<span class="text-xs" style:color={storeColors.of(s.store_id)}>
							{storeColors.name(s.store_id)}
						</span>
					{/if}
					{#if s.source === 'manual'}
						{@render manualTag()}
					{/if}
					<span class="flex-1"></span>
					{#if onrestore}
						<button
							onclick={() => onrestore(s)}
							disabled={busy.has(s.id)}
							class="inline-flex items-center gap-1 text-xs text-primary hover:underline disabled:opacity-40"
						>
							<RotateCcw class="size-3" /> Restore
						</button>
					{/if}
					{#if ondelete && s.source === 'manual'}
						<button
							onclick={() => ondelete(s)}
							disabled={busy.has(s.id)}
							title="Delete this hand-added reading"
							aria-label="Delete this hand-added reading"
							class="rounded p-1 text-muted-foreground hover:text-rose-500 disabled:opacity-40"
						>
							<Trash2 class="size-3" />
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	</div>
{/if}
