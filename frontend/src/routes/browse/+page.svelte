<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Card from '$lib/components/ui/card';
	import { addWatchlist, browseSorts, setOverride, clearOverride } from '$lib/api.js';

	let stores = $state([]);
	let sortOptions = $state([]);
	let items = $state([]);
	let loading = $state(false);
	let page = $state(1);
	let hasMore = $state(true);

	// override modal
	let editItem = $state(null);
	let editForm = $state({});
	let saving = $state(false);

	let watchedTitle = $state('');

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
		const res = await fetch(`/api/browse?${buildQuery(page)}`).then((r) => r.json());
		items = reset ? res.items : [...items, ...res.items];
		hasMore = res.items.length === 48;
		loading = false;
	}

	async function loadMore() {
		page += 1;
		await search(false);
	}

	async function watch(item) {
		await addWatchlist(item.product.id, null);
		watchedTitle = effectiveTitle(item);
		setTimeout(() => {
			watchedTitle = '';
		}, 3000);
	}

	function stars(rating) {
		if (!rating) return '—';
		return parseFloat(rating).toFixed(1);
	}

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
		const q = encodeURIComponent(`BGG ${effectiveTitle(editItem)}`);
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
			await search(true);
			closeEdit();
		} finally {
			saving = false;
		}
	}

	function effectiveTitle(item) {
		return item.override?.title || item.product.title;
	}
	function effectivePrice(item) {
		if (item.override?.override_price != null) return item.override.override_price;
		return item.latest_price?.price ?? null;
	}
	function effectiveAvailable(item) {
		if (item.override?.override_available != null) return item.override.override_available;
		return item.latest_price?.available ?? false;
	}

	onMount(async () => {
		await fetchMeta();
		await search();
	});
</script>

<div class="space-y-4">
	<h1 class="text-2xl font-bold">Browse</h1>

	<!-- Filters -->
	<Card.Root>
		<Card.Content class="pt-4">
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				<Input
					bind:value={filters.q}
					placeholder="Search name…"
					onkeydown={(e) => e.key === 'Enter' && search()}
				/>
				<select
					bind:value={filters.store_id}
					class="rounded border bg-background px-3 py-2 text-sm"
				>
					<option value="">All stores</option>
					{#each stores as s}<option value={s.id}>{s.name}</option>{/each}
				</select>
				<div class="flex gap-2">
					<Input bind:value={filters.min_price} placeholder="Min ₹" type="number" />
					<Input bind:value={filters.max_price} placeholder="Max ₹" type="number" />
				</div>
				<select
					bind:value={filters.sort}
					onchange={() => search()}
					class="rounded border bg-background px-3 py-2 text-sm"
				>
					{#each sortOptions as opt}
						<option value={opt.key}>{opt.label}</option>
					{/each}
				</select>
			</div>
			<div class="mt-3 flex flex-wrap items-center gap-6">
				<label class="flex cursor-pointer items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={filters.in_stock} class="rounded" />
					In stock only
				</label>
				<label class="flex cursor-pointer items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={filters.has_bgg} class="rounded" />
					Has BGG data
				</label>
				<div class="flex items-center gap-2 text-sm">
					<span>Min BGG rating:</span>
					<Input
						bind:value={filters.min_bgg_rating}
						type="number"
						step="0.5"
						min="1"
						max="10"
						class="w-20"
						placeholder="e.g. 7"
					/>
				</div>
				<Button onclick={() => search()}>Apply</Button>
				<Button
					variant="ghost"
					onclick={() => {
						filters = {
							q: '',
							store_id: '',
							min_price: '',
							max_price: '',
							in_stock: false,
							has_bgg: false,
							min_bgg_rating: '',
							sort: 'title'
						};
						search();
					}}
				>
					Reset
				</Button>
			</div>
		</Card.Content>
	</Card.Root>

	<!-- Results grid -->
	{#if loading && items.length === 0}
		<p class="text-muted-foreground">Loading…</p>
	{:else if items.length === 0}
		<p class="text-muted-foreground">No results. Try adjusting filters.</p>
	{:else}
		<div class="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
			{#each items as item}
				<Card.Root
					class="flex cursor-pointer flex-col"
					onclick={() => goto(`/prices/${item.product.id}`)}
				>
					{#if item.bgg?.thumbnail}
						<img
							src={item.bgg.thumbnail}
							alt={effectiveTitle(item)}
							class="h-32 w-full rounded-t-lg bg-muted/30 object-contain p-2"
						/>
					{:else if item.product.image_url}
						<img
							src={item.product.image_url}
							alt={effectiveTitle(item)}
							class="h-32 w-full rounded-t-lg bg-muted/30 object-contain p-2"
						/>
					{:else}
						<div
							class="flex h-32 w-full items-center justify-center rounded-t-lg bg-muted/30 text-4xl"
						>
							🎲
						</div>
					{/if}

					<Card.Content class="flex flex-1 flex-col gap-2 pt-3 pb-3">
						<div class="flex items-start justify-between gap-1">
							<div class="line-clamp-2 text-sm leading-tight font-medium">
								{effectiveTitle(item)}
							</div>
							<button
								onclick={(e) => {
									e.stopPropagation();
									openEdit(item);
								}}
								class="shrink-0 rounded p-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
								title="Edit / override fields">✏️</button
							>
						</div>

						{#if item.override}
							<Badge variant="outline" class="w-fit text-xs text-amber-600">overridden</Badge>
						{/if}

						{@const price = effectivePrice(item)}
						{@const cap = item.latest_price?.compare_at_price}
						<div class="flex flex-wrap items-center gap-2">
							{#if price != null}
								<span class="text-base font-bold">₹{price.toFixed(0)}</span>
								{#if cap && cap > price}
									<span class="text-xs text-muted-foreground line-through">
										₹{cap.toFixed(0)}
									</span>
									{#if item.discount_pct}
										<Badge class="bg-green-100 text-xs text-green-800">-{item.discount_pct}%</Badge>
									{/if}
								{/if}
							{/if}
							{#if effectiveAvailable(item)}
								<Badge class="bg-green-100 text-xs text-green-800">In stock</Badge>
							{:else}
								<Badge variant="destructive" class="text-xs">OOS</Badge>
							{/if}
						</div>

						{#if item.bgg}
							<div class="flex gap-3 text-xs text-muted-foreground">
								<span>⭐ {stars(item.bgg.avg_rating)}</span>
								{#if item.bgg.rank}<span>#{item.bgg.rank}</span>{/if}
								{#if item.bgg.avg_weight}
									<span>⚖️ {parseFloat(item.bgg.avg_weight).toFixed(1)}</span>
								{/if}
							</div>
							{#if filters.sort === 'value' && item.bgg.bgg_rating && effectivePrice(item)}
								<div class="text-xs text-muted-foreground">
									₹{(effectivePrice(item) / parseFloat(item.bgg.bgg_rating)).toFixed(0)} / rating pt
								</div>
							{/if}
							{#if filters.sort === 'value_weight' && item.bgg.avg_weight && effectivePrice(item)}
								<div class="text-xs text-muted-foreground">
									₹{(effectivePrice(item) / parseFloat(item.bgg.avg_weight)).toFixed(0)} / weight unit
								</div>
							{/if}
						{/if}

						<div class="mt-auto flex flex-wrap gap-1 pt-1">
							{#if item.product.url || item.override?.url}
								<Button
									size="sm"
									variant="outline"
									href={item.override?.url || item.product.url}
									target="_blank"
									class="flex-1 text-xs"
									onclick={(e) => e.stopPropagation()}
								>
									Store ↗
								</Button>
							{/if}
							{#if item.bgg?.bgg_url}
								<Button
									size="sm"
									variant="outline"
									href={item.bgg.bgg_url}
									target="_blank"
									class="flex-1 text-xs"
									onclick={(e) => e.stopPropagation()}
								>
									BGG ↗
								</Button>
							{:else}
								<Button
									size="sm"
									variant="ghost"
									onclick={(e) => {
										e.stopPropagation();
										window.open(
											`https://www.google.com/search?q=${encodeURIComponent('BGG ' + effectiveTitle(item))}`,
											'_blank'
										);
									}}
									class="flex-1 text-xs text-muted-foreground"
									title="Search BGG on Google"
								>
									Find BGG ↗
								</Button>
							{/if}
							<Button
								size="sm"
								onclick={(e) => {
									e.stopPropagation();
									watch(item);
								}}
								class="flex-1 text-xs"
							>
								+ Watch
							</Button>
						</div>
					</Card.Content>
				</Card.Root>
			{/each}
		</div>

		{#if hasMore}
			<div class="flex justify-center pt-4">
				<Button variant="outline" onclick={loadMore} disabled={loading}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	{/if}
</div>

{#if watchedTitle}
	<div
		class="fixed right-4 bottom-4 z-50 flex items-center gap-3 rounded-lg bg-green-600 px-4 py-3 text-sm text-white shadow-lg"
	>
		<span>✓ {watchedTitle} added to watchlist</span>
		<button onclick={() => (watchedTitle = '')} class="ml-1 text-white/80 hover:text-white"
			>×</button
		>
	</div>
{/if}

<!-- Override modal -->
{#if editItem}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
		<div class="w-full max-w-md rounded-lg bg-background p-6 shadow-xl">
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
						<Button
							size="sm"
							variant="outline"
							onclick={searchBggOnGoogle}
							title="Search Google for this game on BGG"
						>
							Search BGG ↗
						</Button>
					</div>
					<div class="mt-1 flex gap-2">
						<Input
							bind:value={editForm._bggUrlRaw}
							placeholder="Paste BGG URL to auto-fill ID"
							class="flex-1 text-xs"
							onpaste={onBggUrlPaste}
							oninput={() => {
								const id = parseBggUrl(editForm._bggUrlRaw);
								if (id) editForm.bgg_id = id;
							}}
						/>
					</div>
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
							class="mt-1 w-full rounded border bg-background px-3 py-2 text-sm"
						>
							<option value="">— keep scraped —</option>
							<option value="true">In stock</option>
							<option value="false">Out of stock</option>
						</select>
					</label>
				</div>
				<label class="block text-sm">
					<span class="text-muted-foreground">Note (why you overrode this)</span>
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
						Clear all overrides
					</Button>
				{/if}
			</div>
		</div>
	</div>
{/if}
