<script>
	import { onMount } from 'svelte';
	import { getHidden } from '$lib/api.js';
	import { hidden as hiddenStore } from '$lib/hidden.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { EyeOff } from '@lucide/svelte';

	let items = $state([]);
	let loading = $state(true);

	// Drop cards as soon as they're unhidden (store change), without a refetch.
	const visible = $derived(items.filter((it) => hiddenStore.has(it.product.id)));

	async function load() {
		loading = true;
		try {
			const res = await getHidden(1, 500);
			items = res.items;
		} catch (e) {
			toast.error('Failed to load hidden games: ' + e.message);
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<div class="space-y-5">
	<div>
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<EyeOff class="size-6 text-primary" /> Hidden
		</h1>
		<p class="mt-1 text-sm text-muted-foreground">
			Games you've permanently hidden from browse, drops, new and search. Unhide to bring one back.
		</p>
	</div>

	{#if loading}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each Array(8) as _}
				<div class="space-y-2 rounded-xl border p-3">
					<Skeleton class="aspect-[4/3] w-full" />
					<Skeleton class="h-4 w-3/4" />
					<Skeleton class="h-4 w-1/2" />
				</div>
			{/each}
		</div>
	{:else if visible.length === 0}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<EyeOff class="size-10 text-muted-foreground/40" />
			<p class="font-medium">Nothing hidden</p>
			<p class="text-sm text-muted-foreground">Hide a game from any card and it'll show up here.</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each visible as item (item.product.id)}
				<ProductCard {item} />
			{/each}
		</div>
	{/if}
</div>
