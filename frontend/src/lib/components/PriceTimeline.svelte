<script>
	import { ChevronDown } from '@lucide/svelte';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { inr } from '$lib/gamePricing.js';
	import { fmtDateParts } from '$lib/dateFormat.svelte.js';

	let { events = /** @type {Array<any>} */ ([]), multiStore = false, limit = 12 } = $props();

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

{#snippet row(e, nested = false)}
	{@const color = storeColors.of(e.store_id)}
	<li class="relative flex gap-3 py-2.5 {nested ? 'pl-6' : ''}">
		<span
			class="mt-1.5 size-2.5 shrink-0 rounded-full"
			style:background-color={e.available ? color : 'transparent'}
			style:box-shadow="inset 0 0 0 1.5px {color}"
		></span>
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
				{#if e.kind === 'drop' || e.kind === 'rise'}
					<span class="text-sm text-muted-foreground tabular-nums line-through">
						{inr(e.prevPrice)}
					</span>
					<span
						class="text-sm font-semibold tabular-nums {e.kind === 'drop'
							? 'text-green-600 dark:text-green-400'
							: 'text-rose-500'}"
					>
						{inr(e.price)}
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
					<span class="text-sm tabular-nums">{inr(e.price)}</span>
				{:else}
					<span class="text-sm">
						{e.kind === 'listed'
							? 'First seen'
							: e.kind === 'oos'
								? 'Out of stock'
								: 'Back in stock'}
					</span>
					<span class="text-sm font-semibold tabular-nums">{inr(e.price)}</span>
				{/if}
				{#if multiStore}
					<span class="text-xs" style:color>{storeColors.name(e.store_id)}</span>
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
