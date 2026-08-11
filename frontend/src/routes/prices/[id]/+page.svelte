<script>
	// Old listing URLs (and notification links) resolve to the game that listing
	// belongs to, opening on that shop's tab.
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { gameForListing } from '$lib/api.js';
	import Skeleton from '$lib/components/Skeleton.svelte';

	let failed = $state(false);

	$effect(() => {
		const productId = Number($page.params.id);
		gameForListing(productId)
			.then(({ game_id, store_id }) =>
				goto(`/games/${game_id}?store=${encodeURIComponent(store_id)}`, { replaceState: true })
			)
			.catch(() => (failed = true));
	});
</script>

{#if failed}
	<p class="text-destructive">Product not found</p>
{:else}
	<div class="grid gap-6 md:grid-cols-[260px_1fr]">
		<Skeleton class="aspect-square w-full rounded-xl" />
		<div class="space-y-3">
			<Skeleton class="h-8 w-2/3" />
			<Skeleton class="h-5 w-40" />
			<Skeleton class="h-20 w-full" />
		</div>
	</div>
{/if}
