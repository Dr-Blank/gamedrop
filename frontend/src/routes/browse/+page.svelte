<script>
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Card from '$lib/components/ui/card';
	import { addWatchlist, browseSorts, setOverride, clearOverride } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { Compass, SlidersHorizontal, Search, X } from '@lucide/svelte';

	let stores = $state([]);
	let sortOptions = $state([]);
	let items = $state([]);
	let loading = $state(false);
	let page = $state(1);
	let hasMore = $state(true);
	let showFilters = $state(false);

	// override modal
	let editItem = $state(null);
	let editForm = $state({});
	let saving = $state(false);

	let filters = $state({
		q: '',
		store_id: '',
		min_price: '',
		max_price: '',
		in_stock: false,
		has_bgg: false,
		min_bgg_rating: '',
		sort: 'title'
	});

	const defaults = {
		q: '',
		store_id: '',
		min_price: '',
		max_price: '',
		in_stock: false,
		has_bgg: false,
		min_bgg_rating: '',
		sort: 'title'
	};

	const activeFilterCount = $derived(
		['store_id', 'min_price', 'max_price', 'min_bgg_rating'].filter((k) => filters[k]).length +
			(filters.in_stock ? 1 : 0) +
			(filters.has_bgg ? 1 : 0)
	);

	async function fetchMeta() {
		const [storeRes, sortRes] = await Promise.all([
			fetch('/api/browse/stores').then((r) => r.json()),
			browseSorts()
		]);
		stores = storeRes;
		sortOptions = sortRes;
	}

	function buildQuery(p = 1) {
		const params = new URLSearchParams({ page: String(p), limit: '48' });
		if (filters.q) params.set('q', filters.q);
		if (filters.store_id) params.set('store_id', filters.store_id);
		if (filters.min_price) params.set('min_price', filters.min_price);
		if (filters.max_price) params.set('max_price', filters.max_price);
		if (filters.in_stock) params.set('in_stock', 'true');
		if (filters.has_bgg) params.set('has_bgg', 'true');
		if (filters.min_bgg_rating) params.set('min_bgg_rating', filters.min_bgg_rating);
		params.set('sort', filters.sort);
		return params;
	}

	async function search(reset = true) {
		loading = true;
		if (reset) {
			page = 1;
			items = [];
		}
		try {
			const res = await fetch(`/api/browse?${buildQuery(page)}`).then((r) => r.json());
			items = reset ? res.items : [...items, ...res.items];
			hasMore = res.items.length === 48;
		} catch (e) {
			toast.error('Failed to load: ' + e.message);
		} finally {
			loading = false;
		}
	}

	async function loadMore() {
		page += 1;
		await search(false);
	}

	function resetFilters() {
		filters = { ...defaults };
		search();
	}

	async function watch(item) {
		await addWatchlist(item.product.id, null);
		toast.success(`Watching ${item.override?.title || item.product.title}`);
	}

	// ---- override modal ----
	function parseBggUrl(input) {
		const m = input.match(/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i);
		return m ? m[1] : null;
	}
	function onBggUrlPaste(e) {
		const val = e.clipboardData?.getData('text') ?? e.target.value;
		const id = parseBggUrl(val);
		if (id) {
			editForm.bgg_id = id;
			editForm._bggPasted = true;
		}
	}
	function searchBggOnGoogle() {
		const q = encodeURIComponent(`BGG ${editItem.override?.title || editItem.product.title}`);
		window.open(`https://www.google.com/search?q=${q}`, '_blank');
	}
	function openEdit(item) {
		editItem = item;
		const ov = item.override ?? {};
		editForm = {
			title: ov.title ?? '',
			url: ov.url ?? '',
			bgg_id: ov.bgg_id ?? item.product.bgg_id ?? '',
			override_price: ov.override_price ?? '',
			override_available: ov.override_available ?? '',
			note: ov.note ?? '',
			_bggPasted: false,
			_bggUrlRaw: ''
		};
	}
	function closeEdit() {
		editItem = null;
		editForm = {};
	}
	async function saveOverride() {
		saving = true;
		try {
			const body = {};
			if (editForm.title) body.title = editForm.title;
			if (editForm.url) body.url = editForm.url;
			if (editForm.bgg_id !== '') body.bgg_id = Number(editForm.bgg_id) || null;
			if (editForm.override_price !== '')
				body.override_price = Number(editForm.override_price) || null;
			if (editForm.override_available !== '')
				body.override_available =
					editForm.override_available === true || editForm.override_available === 'true';
			if (editForm.note) body.note = editForm.note;
			await setOverride(editItem.product.id, body);
			toast.success('Override saved');
			await search(true);
			closeEdit();
		} finally {
			saving = false;
		}
	}
	async function removeOverride() {
		if (!confirm('Remove all overrides for this item?')) return;
		saving = true;
		try {
			await clearOverride(editItem.product.id);
			toast.success('Overrides cleared');
			await search(true);
			closeEdit();
		} finally {
			saving = false;
		}
	}

	onMount(async () => {
		await fetchMeta();
		await search();
	});
</script>

<div class="space-y-5">
	<div class="flex items-center justify-between gap-3">
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<Compass class="size-6 text-primary" /> Browse
		</h1>
	</div>

	<!-- Search + filter toggle -->
	<div class="flex flex-col gap-2 sm:flex-row">
		<div class="relative flex-1">
			<Search
				class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
			/>
			<Input
				bind:value={filters.q}
				placeholder="Search games…"
				class="pl-9"
				onkeydown={(e) => e.key === 'Enter' && search()}
			/>
		</div>
		<select
			bind:value={filters.sort}
			onchange={() => search()}
			class="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm transition-colors hover:bg-muted/50"
		>
			{#each sortOptions as opt}<option value={opt.key}>{opt.label}</option>{/each}
		</select>
		<Button
			variant="outline"
			onclick={() => (showFilters = !showFilters)}
			aria-expanded={showFilters}
		>
			<SlidersHorizontal class="size-4" /> Filters
			{#if activeFilterCount}
				<span
					class="ml-1 grid size-5 place-items-center rounded-full bg-primary text-xs text-primary-foreground"
				>
					{activeFilterCount}
				</span>
			{/if}
		</Button>
		<Button onclick={() => search()}>Apply</Button>
	</div>

	<!-- Filter panel -->
	{#if showFilters}
		<div transition:fly={{ y: -8, duration: 200 }}>
			<Card.Root>
				<Card.Content class="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
					<label class="space-y-1 text-sm">
						<span class="text-muted-foreground">Store</span>
						<select
							bind:value={filters.store_id}
							class="h-9 w-full rounded-lg border bg-background px-3 text-sm"
						>
							<option value="">All stores</option>
							{#each stores as s}<option value={s.id}>{s.name}</option>{/each}
						</select>
					</label>
					<label class="space-y-1 text-sm">
						<span class="text-muted-foreground">Price range (₹)</span>
						<div class="flex gap-2">
							<Input bind:value={filters.min_price} placeholder="Min" type="number" />
							<Input bind:value={filters.max_price} placeholder="Max" type="number" />
						</div>
					</label>
					<label class="space-y-1 text-sm">
						<span class="text-muted-foreground">Min BGG rating</span>
						<Input
							bind:value={filters.min_bgg_rating}
							type="number"
							step="0.5"
							min="1"
							max="10"
							placeholder="e.g. 7"
						/>
					</label>
					<div class="flex flex-col justify-end gap-2 text-sm">
						<label class="flex cursor-pointer items-center gap-2">
							<input type="checkbox" bind:checked={filters.in_stock} class="size-4 rounded" />
							In stock only
						</label>
						<label class="flex cursor-pointer items-center gap-2">
							<input type="checkbox" bind:checked={filters.has_bgg} class="size-4 rounded" />
							Has BGG data
						</label>
					</div>
					<div class="flex gap-2 sm:col-span-2 lg:col-span-4">
						<Button onclick={() => search()}>Apply filters</Button>
						<Button variant="ghost" onclick={resetFilters}>
							<X class="size-4" /> Reset
						</Button>
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}

	<!-- Results -->
	{#if loading && items.length === 0}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each Array(12) as _}
				<div class="space-y-2 rounded-xl border p-3">
					<Skeleton class="aspect-[4/3] w-full" />
					<Skeleton class="h-4 w-3/4" />
					<Skeleton class="h-4 w-1/2" />
				</div>
			{/each}
		</div>
	{:else if items.length === 0}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<Search class="size-10 text-muted-foreground/40" />
			<p class="font-medium">No results</p>
			<p class="text-sm text-muted-foreground">Try adjusting your filters.</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each items as item (item.product.id)}
				<ProductCard {item} variant="browse" onwatch={watch} onedit={openEdit} />
			{/each}
		</div>

		{#if hasMore}
			<div class="flex justify-center pt-2">
				<Button variant="outline" onclick={loadMore} disabled={loading}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	{/if}
</div>

<!-- Override modal -->
{#if editItem}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
		transition:fly={{ duration: 150 }}
	>
		<div
			class="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl"
			transition:fly={{ y: 12 }}
		>
			<h2 class="mb-1 text-lg font-semibold">Override fields</h2>
			<p class="mb-4 text-xs text-muted-foreground">
				Values here take priority over scraped data. Leave blank to keep scraped value.
			</p>

			<div class="space-y-3">
				<label class="block text-sm">
					<span class="text-muted-foreground">Title</span>
					<Input bind:value={editForm.title} placeholder={editItem.product.title} class="mt-1" />
				</label>
				<label class="block text-sm">
					<span class="text-muted-foreground">URL</span>
					<Input bind:value={editForm.url} placeholder={editItem.product.url ?? ''} class="mt-1" />
				</label>
				<div class="block text-sm">
					<span class="text-muted-foreground">BGG ID</span>
					<div class="mt-1 flex gap-2">
						<Input
							bind:value={editForm.bgg_id}
							type="number"
							placeholder={editItem.product.bgg_id ?? 'e.g. 167791'}
							class="flex-1"
						/>
						<Button size="sm" variant="outline" onclick={searchBggOnGoogle}>Search BGG ↗</Button>
					</div>
					<Input
						bind:value={editForm._bggUrlRaw}
						placeholder="Paste BGG URL to auto-fill ID"
						class="mt-2 text-xs"
						onpaste={onBggUrlPaste}
						oninput={() => {
							const id = parseBggUrl(editForm._bggUrlRaw);
							if (id) editForm.bgg_id = id;
						}}
					/>
					{#if editForm._bggPasted}
						<p class="mt-0.5 text-xs text-green-600">✓ BGG ID extracted from URL</p>
					{/if}
				</div>
				<div class="grid grid-cols-2 gap-3">
					<label class="block text-sm">
						<span class="text-muted-foreground">Override price (₹)</span>
						<Input
							bind:value={editForm.override_price}
							type="number"
							placeholder={editItem.latest_price?.price ?? ''}
							class="mt-1"
						/>
					</label>
					<label class="block text-sm">
						<span class="text-muted-foreground">Override stock</span>
						<select
							bind:value={editForm.override_available}
							class="mt-1 h-9 w-full rounded-lg border bg-background px-3 text-sm"
						>
							<option value="">— keep scraped —</option>
							<option value="true">In stock</option>
							<option value="false">Out of stock</option>
						</select>
					</label>
				</div>
				<label class="block text-sm">
					<span class="text-muted-foreground">Note</span>
					<Input
						bind:value={editForm.note}
						placeholder="e.g. price includes shipping"
						class="mt-1"
					/>
				</label>
			</div>

			<div class="mt-5 flex items-center gap-2">
				<Button onclick={saveOverride} disabled={saving}>
					{saving ? 'Saving…' : 'Save overrides'}
				</Button>
				<Button variant="ghost" onclick={closeEdit}>Cancel</Button>
				{#if editItem.override}
					<Button variant="destructive" class="ml-auto" onclick={removeOverride} disabled={saving}>
						Clear all
					</Button>
				{/if}
			</div>
		</div>
	</div>
{/if}
