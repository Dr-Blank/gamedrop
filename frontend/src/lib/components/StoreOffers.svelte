<script>
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import Sparkline from './Sparkline.svelte';
	import { inr } from '$lib/gamePricing.js';
	import { ExternalLink, Check, Unlink, TrendingDown } from '@lucide/svelte';

	let {
		compare,
		currentProductId = /** @type {number|null} */ (null),
		onselect = /** @type {((productId:number)=>void)|null} */ (null),
		onunmerge = /** @type {((productId:number)=>void)|null} */ (null)
	} = $props();

	const offers = $derived(compare?.offers ?? []);
	const bestInStock = $derived(compare?.cheapest_in_stock ?? null);
	const cheapest = $derived(compare?.cheapest ?? null);
	const cheaperButOut = $derived(
		bestInStock && cheapest && cheapest.product_id !== bestInStock.product_id ? cheapest : null
	);
</script>

<div class="space-y-3">
	{#if cheaperButOut}
		<p class="flex items-center gap-1.5 text-xs text-muted-foreground">
			<TrendingDown class="size-3.5 text-rose-500" />
			Cheapest is {inr(cheaperButOut.price)} at
			<span class="font-medium">{cheaperButOut.store_id}</span> but out of stock — buyable from
			{inr(bestInStock.price)}.
		</p>
	{:else if !bestInStock}
		<p class="text-xs text-rose-500">Out of stock at every store in this group.</p>
	{/if}

	<div class="overflow-hidden rounded-lg border">
		<table class="w-full text-sm">
			<thead class="bg-muted/50 text-muted-foreground">
				<tr>
					<th class="px-3 py-2 text-left font-medium">Store</th>
					<th class="px-3 py-2 text-right font-medium">Price</th>
					<th class="px-3 py-2 text-center font-medium">Stock</th>
					<th class="px-3 py-2 text-center font-medium">Trend</th>
					<th class="px-3 py-2"></th>
				</tr>
			</thead>
			<tbody class="divide-y">
				{#each offers as offer (offer.product_id)}
					{@const isBest = bestInStock?.product_id === offer.product_id}
					<tr
						class="transition-colors hover:bg-muted/30 {isBest
							? 'bg-green-500/5'
							: ''} {offer.product_id === currentProductId ? 'font-medium' : ''}"
					>
						<td class="px-3 py-2">
							<button
								class="text-left hover:underline"
								onclick={() => onselect?.(offer.product_id)}
							>
								{offer.store_id}
							</button>
							{#if offer.product_id === currentProductId}
								<span class="ml-1 text-[0.7rem] text-muted-foreground">(shown)</span>
							{/if}
						</td>
						<td class="px-3 py-2 text-right tabular-nums">
							<span class={offer.available ? '' : 'text-muted-foreground line-through'}>
								{inr(offer.price)}
							</span>
							{#if isBest}
								<Badge
									class="ml-1.5 gap-1 border-green-500/25 bg-green-500/15 text-[0.65rem] text-green-600 dark:text-green-400"
								>
									<Check class="size-3" /> best
								</Badge>
							{/if}
						</td>
						<td class="px-3 py-2 text-center">
							{#if offer.available}
								<span class="text-green-600 dark:text-green-400" title="In stock">●</span>
							{:else}
								<span class="text-destructive" title="Out of stock">✕</span>
							{/if}
						</td>
						<td class="px-3 py-2">
							<div class="flex justify-center">
								<Sparkline history={offer.price_history ?? []} width={80} height={22} />
							</div>
						</td>
						<td class="px-3 py-2">
							<div class="flex items-center justify-end gap-1">
								{#if offer.url}
									<Button
										size="icon-sm"
										variant="ghost"
										href={offer.url}
										target="_blank"
										title="Open at store"
									>
										<ExternalLink class="size-3.5" />
									</Button>
								{/if}
								{#if onunmerge}
									<Button
										size="icon-sm"
										variant="ghost"
										title="Remove from this group"
										onclick={() => onunmerge(offer.product_id)}
									>
										<Unlink class="size-3.5" />
									</Button>
								{/if}
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
