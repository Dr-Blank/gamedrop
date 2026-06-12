<script>
	import { Star, Trophy, Scale } from '@lucide/svelte';
	let { bgg = /** @type {any} */ (null), class: className = '' } = $props();

	const rating = $derived(bgg?.avg_rating ? parseFloat(bgg.avg_rating).toFixed(1) : null);
	const weight = $derived(bgg?.avg_weight ? parseFloat(bgg.avg_weight).toFixed(1) : null);
</script>

{#if bgg && (rating || bgg.rank || weight)}
	<div
		class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground {className}"
	>
		{#if rating}
			<span class="inline-flex items-center gap-1">
				<Star class="size-3.5 fill-amber-400 text-amber-400" />
				<span class="font-medium text-foreground">{rating}</span>
			</span>
		{/if}
		{#if bgg.rank}
			<span class="inline-flex items-center gap-1">
				<Trophy class="size-3.5" /># {bgg.rank}
			</span>
		{/if}
		{#if weight}
			<span class="inline-flex items-center gap-1" title="Complexity (1–5)">
				<Scale class="size-3.5" />{weight}
			</span>
		{/if}
	</div>
{/if}
