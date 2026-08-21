<script>
	import { Badge } from '$lib/components/ui/badge';
	import { inr, roundPrice } from '$lib/priceFormat.svelte.js';

	let {
		price = /** @type {number|null} */ (null),
		compareAt = /** @type {number|null} */ (null),
		discountPct = /** @type {number|null} */ (null),
		size = 'md'
	} = $props();

	const cls = { sm: 'text-sm', md: 'text-base', lg: 'text-2xl' };
	// Rounding can pull an MRP down onto the very price it is meant to sit above.
	const showStrike = $derived(
		compareAt != null && price != null && roundPrice(compareAt) > roundPrice(price)
	);
	const pct = $derived(
		discountPct ?? (showStrike ? Math.round(((compareAt - price) / compareAt) * 100) : null)
	);
</script>

<div class="flex flex-wrap items-baseline gap-1.5">
	{#if price != null}
		<span class="font-bold tabular-nums {cls[size]}">{inr(price)}</span>
		{#if showStrike}
			<span class="text-xs text-muted-foreground tabular-nums line-through">{inr(compareAt)}</span>
			{#if pct}
				<Badge
					class="border-green-500/25 bg-green-500/15 text-[0.7rem] text-green-600 dark:text-green-400"
				>
					−{pct}%
				</Badge>
			{/if}
		{/if}
	{:else}
		<span class="text-muted-foreground {cls[size]}">—</span>
	{/if}
</div>
