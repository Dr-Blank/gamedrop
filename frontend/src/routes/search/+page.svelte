<script>
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { searchCatalog } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import { Search } from '@lucide/svelte';

	const q = $derived($page.url.searchParams.get('q') ?? '');
	let input = $state('');
	let items = $state([]);
	let loading = $state(false);
	let ran = $state(false);
	let debounceHandle;

	// Keep the box in sync when navigating via the header search.
	$effect(() => {
		input = q;
	});

	// Auto-navigate once the user stops typing, so a search runs without
	// pressing Enter. Enter/click still fires immediately via submit().
	$effect(() => {
		const term = input.trim();
		clearTimeout(debounceHandle);
		if (term === q) return;
		debounceHandle = setTimeout(() => {
			goto(term ? `/search?q=${encodeURIComponent(term)}` : '/search', { keepFocus: true });
		}, 400);
		return () => clearTimeout(debounceHandle);
	});

	// Run a search whenever the URL query changes.
	$effect(() => {
		const term = q;
		if (!term) {
			items = [];
			ran = false;
			return;
		}
		loading = true;
		ran = true;
		searchCatalog(term, 48)
			.then((res) => (items = res.items))
			.catch((e) => toast.error(e.message))
			.finally(() => (loading = false));
	});

	function submit() {
		clearTimeout(debounceHandle);
		const t = input.trim();
		if (t) goto(`/search?q=${encodeURIComponent(t)}`, { keepFocus: true });
	}
</script>

<div class="space-y-5">
	<h1 class="text-2xl font-bold tracking-tight">Search</h1>

	<form
		onsubmit={(e) => {
			e.preventDefault();
			submit();
		}}
		class="flex max-w-xl gap-2"
	>
		<div class="relative flex-1">
			<Search
				class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
			/>
			<Input bind:value={input} placeholder="Search any game…" class="h-11 pl-9" autofocus />
		</div>
		<Button type="submit" size="lg" class="h-11">Search</Button>
	</form>

	{#if loading}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each Array(8) as _}
				<div class="space-y-2 rounded-xl border p-3">
					<Skeleton class="aspect-[4/3] w-full" />
					<Skeleton class="h-4 w-3/4" />
				</div>
			{/each}
		</div>
	{:else if ran && items.length === 0}
		<p class="rounded-xl border border-dashed py-16 text-center text-muted-foreground">
			No games found for “{q}”.
		</p>
	{:else if items.length > 0}
		<p class="text-sm text-muted-foreground">
			{items.length} result{items.length === 1 ? '' : 's'} for “{q}”
		</p>
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each items as item (item.product.id)}
				<ProductCard {item} variant="browse" />
			{/each}
		</div>
	{:else}
		<p class="text-muted-foreground">Type a game name to search across all tracked stores.</p>
	{/if}
</div>
