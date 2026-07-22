<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { fade } from 'svelte/transition';
	import {
		shelvesPreview,
		getWatchlist,
		getShelves,
		patchShelf,
		reorderShelves
	} from '$lib/api.js';
	import { browseUrl } from '$lib/browse.js';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import { shelfIcon } from '$lib/shelfIcons.js';
	import Shelf from '$lib/components/Shelf.svelte';
	import ShelfMenu from '$lib/components/ShelfMenu.svelte';
	import ShelfReorderList from '$lib/components/ShelfReorderList.svelte';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import { Search, Compass, Heart, GripVertical } from '@lucide/svelte';

	let shelvesList = $state(/** @type {any[]} */ ([]));
	let watchlistItems = $state(/** @type {any[]} */ ([]));
	let loading = $state(true);
	let q = $state('');

	// Reorder mode: shelves collapse to draggable rows; order saves on exit.
	let editing = $state(false);
	let editOrder = $state(/** @type {any[]} */ ([]));
	let hiddenShelves = $state(/** @type {any[]} */ ([]));

	function shelfBrowseUrl(shelf) {
		return browseUrl({
			filters: shelf.filters ? JSON.parse(shelf.filters) : null,
			sorts: shelf.sorts ? JSON.parse(shelf.sorts) : []
		});
	}

	async function load() {
		loading = true;
		try {
			const [preview, wl] = await Promise.all([shelvesPreview(8), getWatchlist()]);
			shelvesList = preview;
			watchlistItems = wl;
		} catch (e) {
			toast.error('Failed to load: ' + e.message);
		} finally {
			loading = false;
		}
	}

	function submitSearch() {
		if (q.trim()) goto(`/search?q=${encodeURIComponent(q.trim())}`);
	}

	/** Persist the running order of the visible shelves. Hidden shelves are not
	 * listed, so the backend keeps them after the visible ones.
	 * @param {any[]} shelves */
	async function saveOrder(shelves) {
		try {
			await reorderShelves(shelves.map((s) => s.id));
		} catch (e) {
			toast.error('Failed to save shelf order: ' + e.message);
		}
	}

	/** Quick reorder from a shelf's own menu — saves right away.
	 * @param {number} index @param {number} dir */
	async function moveShelf(index, dir) {
		const to = index + dir;
		if (to < 0 || to >= shelvesList.length) return;
		const next = [...shelvesList];
		[next[index], next[to]] = [next[to], next[index]];
		shelvesList = next;
		await saveOrder(next.map((row) => row.shelf));
	}

	/** @param {any} shelf */
	async function hideShelf(shelf) {
		try {
			await patchShelf(shelf.id, { hidden: true });
			shelvesList = shelvesList.filter((row) => row.shelf.id !== shelf.id);
			editOrder = editOrder.filter((s) => s.id !== shelf.id);
			hiddenShelves = [...hiddenShelves, { ...shelf, hidden: true }];
			toast.success(`Removed ${shelf.name} from home`);
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {any} shelf */
	async function unhideShelf(shelf) {
		try {
			await patchShelf(shelf.id, { hidden: false });
			hiddenShelves = hiddenShelves.filter((s) => s.id !== shelf.id);
			editOrder = [...editOrder, { ...shelf, hidden: false }];
			toast.success(`Added ${shelf.name} to home`);
		} catch (e) {
			toast.error(e.message);
		}
	}

	async function startEditing() {
		editOrder = shelvesList.map((row) => row.shelf);
		editing = true;
		try {
			const all = await getShelves();
			hiddenShelves = all.filter((s) => s.hidden);
		} catch (e) {
			toast.error('Failed to load hidden shelves: ' + e.message);
		}
	}

	async function finishEditing() {
		editing = false;
		await saveOrder(editOrder);
		await load();
	}

	onMount(load);
</script>

<div class="space-y-8">
	<!-- Hero -->
	<section
		class="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-background to-background p-6 sm:p-10"
	>
		<div class="relative z-10 max-w-2xl space-y-3">
			<h1 class="text-3xl font-bold tracking-tight sm:text-4xl">
				Never overpay for a board game again
			</h1>
			<p class="text-muted-foreground">
				Track prices across stores, catch every drop, and pounce when it hits your target.
			</p>
			<form
				onsubmit={(e) => {
					e.preventDefault();
					submitSearch();
				}}
				class="flex max-w-md gap-2 pt-1"
			>
				<div class="relative flex-1">
					<Search
						class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
					/>
					<Input bind:value={q} placeholder="Search any game…" class="h-11 pl-9" />
				</div>
				<Button type="submit" size="lg" class="h-11">Search</Button>
			</form>
		</div>
		<Compass
			class="pointer-events-none absolute -right-8 -bottom-8 size-48 text-primary/5"
			strokeWidth={1}
		/>
	</section>

	{#snippet skeletonCard()}
		<div class="space-y-2 rounded-xl border p-3">
			<Skeleton class="aspect-[4/3] w-full" />
			<Skeleton class="h-4 w-3/4" />
			<Skeleton class="h-4 w-1/2" />
		</div>
	{/snippet}

	{#if loading}
		<div class="space-y-8" in:fade>
			{#each Array(4) as _}
				<Shelf title="Loading…" loading={true} skeleton={skeletonCard} card={() => {}} />
			{/each}
		</div>
	{:else if editing}
		<div in:fade={{ duration: 150 }}>
			<ShelfReorderList
				bind:shelves={editOrder}
				hidden={hiddenShelves}
				onhide={hideShelf}
				onunhide={unhideShelf}
				ondone={finishEditing}
			/>
		</div>
	{:else}
		<div class="space-y-8" in:fade={{ duration: 150 }}>
			<div class="flex justify-end">
				<Button variant="ghost" size="sm" onclick={startEditing} class="text-muted-foreground">
					<GripVertical class="size-4" /> Edit shelves
				</Button>
			</div>

			<!-- Dynamic shelves from backend -->
			{#each shelvesList as { shelf, items }, i (shelf.id)}
				{@const Icon = shelfIcon(shelf.icon)}
				<Shelf
					title={shelf.name}
					icon={Icon}
					href={shelfBrowseUrl(shelf)}
					{items}
					empty="Nothing here yet."
				>
					{#snippet card(item)}
						<ProductCard {item} variant="browse" />
					{/snippet}
					{#snippet actions()}
						<ShelfMenu
							canMoveUp={i > 0}
							canMoveDown={i < shelvesList.length - 1}
							onmoveup={() => moveShelf(i, -1)}
							onmovedown={() => moveShelf(i, 1)}
							onhide={() => hideShelf(shelf)}
							onreorder={startEditing}
						/>
					{/snippet}
				</Shelf>
			{/each}

			<!-- Watchlist (special — not a filter shelf) -->
			{#if watchlistItems.length > 0}
				<Shelf
					title="Your watchlist"
					icon={Heart}
					href="/watchlist"
					items={watchlistItems.slice(0, 8)}
					empty="Your watchlist is empty."
				>
					{#snippet card(item)}
						<ProductCard
							{item}
							variant="watchlist"
							target={item.watchlist?.target_price}
							onremove={() => watchlist.toggle(item).then(load)}
						/>
					{/snippet}
				</Shelf>
			{/if}

			<!-- Browse CTA -->
			<div class="flex items-center justify-center py-4">
				<Button href="/browse" variant="outline" size="lg">
					<Compass class="size-4" /> Browse all games
				</Button>
			</div>
		</div>
	{/if}
</div>
