<script>
	// Prices found elsewhere — a listing's past, from before it was tracked.
	import { Plus } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { storeColors } from '$lib/storeColors.svelte.js';

	let {
		listings = /** @type {Array<{product_id:number, store_id:string}>} */ ([]),
		busy = false,
		onadd = /** @type {((entry: any) => void) | null} */ (null)
	} = $props();

	const today = new Date().toISOString().slice(0, 10);

	let productId = $state(/** @type {number | null} */ (null));
	let price = $state('');
	let day = $state(today);
	let available = $state(true);

	const target = $derived(productId ?? listings[0]?.product_id ?? null);
	const valid = $derived(target != null && day !== '' && Number(price) > 0);

	function submit() {
		if (!valid || !onadd) return;
		onadd({
			product_id: target,
			price: Number(price),
			// Midday, so a date typed here can't land on the wrong day once the
			// browser's offset is applied.
			recorded_at: `${day}T12:00:00`,
			available
		});
		price = '';
	}
</script>

<form
	class="flex flex-wrap items-end gap-2 rounded-lg border border-dashed p-3"
	onsubmit={(e) => {
		e.preventDefault();
		submit();
	}}
>
	{#if listings.length > 1}
		<label class="text-xs">
			<span class="text-muted-foreground">Shop</span>
			<select
				bind:value={productId}
				class="mt-1 block h-9 rounded-lg border bg-background px-2 text-sm"
			>
				{#each listings as l (l.product_id)}
					<option value={l.product_id}>{storeColors.name(l.store_id)}</option>
				{/each}
			</select>
		</label>
	{/if}

	<label class="text-xs">
		<span class="text-muted-foreground">Date</span>
		<Input type="date" bind:value={day} max={today} class="mt-1 w-40" />
	</label>

	<label class="text-xs">
		<span class="text-muted-foreground">Price</span>
		<Input type="number" min="0" step="0.01" bind:value={price} placeholder="0" class="mt-1 w-28" />
	</label>

	<label class="mb-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
		<input type="checkbox" bind:checked={available} class="size-3.5 rounded border" />
		In stock
	</label>

	<Button type="submit" size="sm" disabled={!valid || busy} class="mb-0.5">
		<Plus class="size-4" /> Add price
	</Button>
</form>
