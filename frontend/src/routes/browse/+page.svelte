<script>
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto, afterNavigate } from '$app/navigation';
	import { fly } from 'svelte/transition';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Card from '$lib/components/ui/card';
	import * as Dialog from '$lib/components/ui/dialog';
	import {
		browseFields,
		browseQuery,
		browseStores,
		createShelf,
		setOverride,
		clearOverride
	} from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import FilterGroup from '$lib/components/FilterGroup.svelte';
	import {
		Compass,
		SlidersHorizontal,
		Plus,
		X,
		Bookmark,
		ArrowUp,
		ArrowDown,
		Trash2
	} from '@lucide/svelte';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------

	let fields = $state([]);
	let items = $state([]);
	let total = $state(0);
	let loading = $state(false);
	let page_ = $state(1);
	let showFilters = $state(false);
	let saveOpen = $state(false);
	let saveName = $state('');
	let saveIcon = $state('Layers');
	let saving = $state(false);

	// Root filter group — always AND at the top level
	let filterTree = $state({ type: 'group', op: 'and', conditions: [] });

	// Sorts list: [{field, dir}]
	let sorts = $state([]);

	// Override modal
	let editItem = $state(null);
	let editForm = $state({});
	let editSaving = $state(false);

	const LIMIT = 48;
	const hasFilters = $derived(filterTree.conditions.length > 0);
	const hasSorts = $derived(sorts.length > 0);

	// When explicitly filtering hidden=true, show hidden variant so cards render
	const browsingHidden = $derived(
		filterTree.conditions.some(
			(c) => c.type === 'condition' && c.field === 'hidden' && c.op === 'eq' && c.value === true
		)
	);

	// ---------------------------------------------------------------------------
	// URL ↔ state encoding
	// ---------------------------------------------------------------------------

	function encodeState() {
		const f = hasFilters ? btoa(JSON.stringify(filterTree)) : null;
		const s = hasSorts ? btoa(JSON.stringify(sorts)) : null;
		const params = new URLSearchParams();
		if (f) params.set('f', f);
		if (s) params.set('s', s);
		return params.toString();
	}

	function decodeFromUrl() {
		const url = $page.url;
		const f = url.searchParams.get('f');
		const s = url.searchParams.get('s');
		if (f) {
			try {
				const parsed = JSON.parse(atob(f));
				// Shelf filters may be a bare Condition — always wrap in a Group for the UI
				if (parsed.type === 'condition') {
					filterTree = { type: 'group', op: 'and', conditions: [parsed] };
				} else {
					filterTree = parsed;
				}
			} catch {}
		}
		if (s) {
			try {
				sorts = JSON.parse(atob(s));
			} catch {}
		}
	}

	function pushUrl() {
		const qs = encodeState();
		const newUrl = qs ? `/browse?${qs}` : '/browse';
		goto(newUrl, { replaceState: true, noScroll: true, keepFocus: true });
	}

	// ---------------------------------------------------------------------------
	// Query
	// ---------------------------------------------------------------------------

	async function search(reset = true) {
		loading = true;
		if (reset) {
			page_ = 1;
			items = [];
		}
		try {
			const body = {
				filters: hasFilters ? filterTree : null,
				sorts,
				page: page_,
				limit: LIMIT
			};
			const res = await browseQuery(body);
			items = reset ? res.items : [...items, ...res.items];
			total = res.total;
		} catch (e) {
			toast.error('Failed to load: ' + e.message);
		} finally {
			loading = false;
		}
	}

	async function loadMore() {
		page_ += 1;
		await search(false);
	}

	function applyFilters() {
		pushUrl(); // afterNavigate will decode URL + search
	}

	function resetFilters() {
		filterTree = { type: 'group', op: 'and', conditions: [] };
		sorts = [];
		pushUrl(); // afterNavigate will decode URL + search
	}

	// ---------------------------------------------------------------------------
	// Sorts
	// ---------------------------------------------------------------------------

	function addSort() {
		const used = new Set(sorts.map((s) => s.field));
		const first = fields.find((f) => f.sortable && !used.has(f.name));
		if (first) sorts.push({ field: first.name, dir: 'asc' });
	}

	function removeSort(i) {
		sorts.splice(i, 1);
	}

	function moveSort(i, dir) {
		const j = i + dir;
		if (j < 0 || j >= sorts.length) return;
		[sorts[i], sorts[j]] = [sorts[j], sorts[i]];
	}

	// ---------------------------------------------------------------------------
	// Save as shelf
	// ---------------------------------------------------------------------------

	async function saveAsShelf() {
		if (!saveName.trim()) return;
		saving = true;
		try {
			await createShelf({
				name: saveName.trim(),
				icon: saveIcon,
				filters: hasFilters ? filterTree : null,
				sorts
			});
			toast.success('Shelf saved!');
			saveOpen = false;
			saveName = '';
		} catch (e) {
			toast.error('Failed to save shelf: ' + e.message);
		} finally {
			saving = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Override modal
	// ---------------------------------------------------------------------------

	function parseBggUrl(input) {
		const m = input.match(/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i);
		return m ? m[1] : null;
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
			_bggUrlRaw: ''
		};
	}

	function closeEdit() {
		editItem = null;
		editForm = {};
	}

	async function saveOverride() {
		editSaving = true;
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
			editSaving = false;
		}
	}

	async function removeOverride() {
		if (!confirm('Remove all overrides for this item?')) return;
		editSaving = true;
		try {
			await clearOverride(editItem.product.id);
			toast.success('Overrides cleared');
			await search(true);
			closeEdit();
		} finally {
			editSaving = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Init
	// ---------------------------------------------------------------------------

	// Load fields once (independent of navigation)
	onMount(async () => {
		fields = await browseFields();
	});

	// Decode URL params and search on every navigation to this route,
	// including initial mount and same-route param changes (nav links).
	afterNavigate(async () => {
		decodeFromUrl();
		await search();
	});
</script>

<div class="space-y-5">
	<!-- Header -->
	<div class="flex items-center justify-between gap-3">
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<Compass class="size-6 text-primary" /> Browse
		</h1>
		<div class="flex gap-2">
			<Button
				variant="outline"
				size="sm"
				onclick={() => (showFilters = !showFilters)}
				aria-expanded={showFilters}
			>
				<SlidersHorizontal class="size-4" />
				Filters
				{#if hasFilters || hasSorts}
					<span
						class="grid size-5 place-items-center rounded-full bg-primary text-xs text-primary-foreground"
					>
						{filterTree.conditions.length + sorts.length}
					</span>
				{/if}
			</Button>
			{#if hasFilters || hasSorts}
				<Button variant="outline" size="sm" onclick={() => (saveOpen = true)}>
					<Bookmark class="size-4" /> Save shelf
				</Button>
			{/if}
		</div>
	</div>

	<!-- Filter + sort panel -->
	{#if showFilters}
		<div transition:fly={{ y: -8, duration: 180 }}>
			<Card.Root>
				<Card.Content class="space-y-4 p-4">
					<!-- Filter builder -->
					<div class="space-y-2">
						<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Filters</p>
						{#if fields.length}
							<FilterGroup bind:group={filterTree} {fields} depth={0} />
						{/if}
					</div>

					<!-- Sort builder -->
					<div class="space-y-2">
						<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">
							Sort priority (first = primary)
						</p>
						<div class="space-y-1.5">
							{#each sorts as sort, i (i)}
								<div class="flex items-center gap-1.5">
									<span class="w-4 text-center text-xs text-muted-foreground">{i + 1}</span>
									<select
										bind:value={sort.field}
										class="h-7 flex-1 rounded border bg-background px-2 text-xs"
									>
										{#each fields.filter((f) => f.sortable) as f}
											<option value={f.name}>{f.label}</option>
										{/each}
									</select>
									<select
										bind:value={sort.dir}
										class="h-7 w-24 rounded border bg-background px-2 text-xs"
									>
										<option value="asc">↑ asc</option>
										<option value="desc">↓ desc</option>
									</select>
									<button
										onclick={() => moveSort(i, -1)}
										disabled={i === 0}
										class="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
									>
										<ArrowUp class="size-3" />
									</button>
									<button
										onclick={() => moveSort(i, 1)}
										disabled={i === sorts.length - 1}
										class="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
									>
										<ArrowDown class="size-3" />
									</button>
									<button
										onclick={() => removeSort(i)}
										class="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
									>
										<Trash2 class="size-3" />
									</button>
								</div>
							{/each}
							<button
								onclick={addSort}
								class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
							>
								<Plus class="size-3" /> Add sort
							</button>
						</div>
					</div>

					<div class="flex gap-2 pt-1">
						<Button onclick={applyFilters}>Apply</Button>
						<Button variant="ghost" onclick={resetFilters}>
							<X class="size-4" /> Reset
						</Button>
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}

	<!-- Results count -->
	{#if !loading && total > 0}
		<p class="text-sm text-muted-foreground">{total} result{total === 1 ? '' : 's'}</p>
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
	{:else if items.length === 0 && !loading}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<Compass class="size-10 text-muted-foreground/40" />
			<p class="font-medium">No results</p>
			<p class="text-sm text-muted-foreground">Try adjusting your filters.</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each items as item (item.product.id)}
				<ProductCard
					{item}
					variant={browsingHidden ? 'hidden' : 'browse'}
					onedit={openEdit}
					history={item.price_history ?? []}
				/>
			{/each}
		</div>
		{#if items.length < total}
			<div class="flex justify-center pt-2">
				<Button variant="outline" onclick={loadMore} disabled={loading}>
					{loading ? 'Loading…' : `Load more (${total - items.length} remaining)`}
				</Button>
			</div>
		{/if}
	{/if}
</div>

<!-- Save shelf dialog -->
{#if saveOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
		transition:fly={{ duration: 150 }}
	>
		<div
			class="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
			transition:fly={{ y: 12 }}
		>
			<h2 class="mb-4 text-lg font-semibold">Save as shelf</h2>
			<div class="space-y-3">
				<label class="block text-sm">
					<span class="text-muted-foreground">Name</span>
					<Input
						bind:value={saveName}
						placeholder="e.g. Cheap gateway games"
						class="mt-1"
						autofocus
					/>
				</label>
				<label class="block text-sm">
					<span class="text-muted-foreground">Icon</span>
					<select
						bind:value={saveIcon}
						class="mt-1 h-9 w-full rounded-lg border bg-background px-3 text-sm"
					>
						<option value="Layers">Layers</option>
						<option value="Star">Star</option>
						<option value="Heart">Heart</option>
						<option value="Tag">Tag</option>
						<option value="Sparkles">Sparkles</option>
						<option value="TrendingDown">Trending Down</option>
						<option value="Package">Package</option>
						<option value="Zap">Zap</option>
					</select>
				</label>
			</div>
			<div class="mt-5 flex gap-2">
				<Button onclick={saveAsShelf} disabled={saving || !saveName.trim()}>
					{saving ? 'Saving…' : 'Save'}
				</Button>
				<Button variant="ghost" onclick={() => (saveOpen = false)}>Cancel</Button>
			</div>
		</div>
	</div>
{/if}

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
				<label class="block text-sm">
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
							onclick={() =>
								window.open(
									`https://www.google.com/search?q=${encodeURIComponent('BGG ' + (editItem.override?.title || editItem.product.title))}`,
									'_blank'
								)}
						>
							Search ↗
						</Button>
					</div>
					<Input
						bind:value={editForm._bggUrlRaw}
						placeholder="Paste BGG URL to auto-fill ID"
						class="mt-2 text-xs"
						oninput={() => {
							const m = editForm._bggUrlRaw.match(
								/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i
							);
							if (m) editForm.bgg_id = m[1];
						}}
					/>
				</label>
				<div class="grid grid-cols-2 gap-3">
					<label class="block text-sm">
						<span class="text-muted-foreground">Override price</span>
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
				<Button onclick={saveOverride} disabled={editSaving}>
					{editSaving ? 'Saving…' : 'Save overrides'}
				</Button>
				<Button variant="ghost" onclick={closeEdit}>Cancel</Button>
				{#if editItem.override}
					<Button
						variant="destructive"
						class="ml-auto"
						onclick={removeOverride}
						disabled={editSaving}
					>
						Clear all
					</Button>
				{/if}
			</div>
		</div>
	</div>
{/if}
