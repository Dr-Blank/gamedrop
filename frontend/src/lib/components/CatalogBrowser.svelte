<script>
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { tick } from 'svelte';
	import { goto, afterNavigate, beforeNavigate } from '$app/navigation';
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
		patchGame,
		setOverride,
		clearOverride
	} from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import FilterGroup from '$lib/components/FilterGroup.svelte';
	import SortMenu from '$lib/components/SortMenu.svelte';
	import InfiniteScroll from '$lib/components/InfiniteScroll.svelte';
	import { shortcuts, BROWSE_SHORTCUTS } from '$lib/shortcuts.svelte.js';
	import { Compass, SlidersHorizontal, Plus, X, Bookmark, ArrowUpDown } from '@lucide/svelte';

	let {
		title = 'Browse',
		icon = Compass,
		basePath = '/browse',
		/** Always ANDed into the query and never shown in the filter builder. */
		preset = /** @type {any} */ (null),
		includeHidden = false,
		saveShelf = true,
		/** One-click conditions this view keeps in its header. */
		quickFilters = /** @type {Array<{label:string,icon:any,title?:string,condition:any}>} */ ([]),
		/** Ordering the view opens with, until the URL says otherwise. */
		defaultSorts = /** @type {Array<{field:string,dir:string}>} */ ([]),
		subtitle = '',
		emptyTitle = 'No results',
		emptyHint = 'Try adjusting your filters.',
		countLabel = /** @type {((n:number)=>string)|null} */ (null),
		/** Cards stop matching the preset the moment it is undone on the card. */
		stillMatches = /** @type {((item:any)=>boolean)|null} */ (null)
	} = $props();

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------

	let fields = $state([]);
	let stores = $state([]);
	let items = $state([]);
	let total = $state(0);
	let loading = $state(false);
	let page_ = $state(1);
	let showFilters = $state(false);
	let showSort = $state(false);
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
	let _editOriginal = {}; // snapshot at open — used to detect unsaved changes

	const editDirty = $derived(
		JSON.stringify({ ...editForm, _bggUrlRaw: undefined }) !==
			JSON.stringify({ ..._editOriginal, _bggUrlRaw: undefined })
	);

	const PageIcon = $derived(icon);

	const shown = $derived(stillMatches ? items.filter(stillMatches) : items);

	const LIMIT = 48;
	const hasFilters = $derived(filterTree.conditions.length > 0);
	const hasSorts = $derived(sorts.length > 0);

	/** @param {any} condition */
	function quickFilterOn(condition) {
		return filterTree.conditions.some(
			(c) => c.type === 'condition' && c.field === condition.field && c.op === condition.op
		);
	}

	/** @param {any} condition */
	function toggleQuickFilter(condition) {
		filterTree.conditions = quickFilterOn(condition)
			? filterTree.conditions.filter(
					(c) => !(c.type === 'condition' && c.field === condition.field && c.op === condition.op)
				)
			: [...filterTree.conditions, { ...condition }];
		pushUrl();
	}

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
		} else if (defaultSorts.length && !sorts.length) {
			sorts = defaultSorts.map((sort) => ({ ...sort }));
		}
	}

	function pushUrl() {
		const qs = encodeState();
		goto(qs ? `${basePath}?${qs}` : basePath, {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}

	// The preset is the page's identity, not a filter the user picked, so it
	// rides on the query without ever reaching the builder or the URL.
	function queryFilters() {
		const own = hasFilters ? filterTree : null;
		if (!preset) return own;
		return {
			type: 'group',
			op: 'and',
			conditions: own ? [preset, ...filterTree.conditions] : [preset]
		};
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
				filters: queryFilters(),
				sorts,
				page: page_,
				limit: LIMIT,
				include_hidden: includeHidden
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

	// Page-scoped shortcuts — unregistered on navigate, so the help sheet only
	// advertises them here.
	/** Open the filter panel on a store condition, ready to pick a store. */
	function quickStoreFilter() {
		showFilters = true;
		const existing = filterTree.conditions.find(
			(c) => c.type === 'condition' && c.field === 'store_id'
		);
		if (!existing) {
			filterTree.conditions.push({ type: 'condition', field: 'store_id', op: 'eq', value: '' });
		}
		tick().then(() => document.querySelector('[data-field="store_id"]')?.focus());
	}

	$effect(() =>
		shortcuts.register(BROWSE_SHORTCUTS, {
			f: () => (showFilters = !showFilters),
			r: resetFilters,
			'mod+enter': applyFilters,
			'.': quickStoreFilter
		})
	);

	function applyFilters() {
		pushUrl(); // afterNavigate will decode URL + search
	}

	function resetFilters() {
		filterTree = { type: 'group', op: 'and', conditions: [] };
		pushUrl(); // afterNavigate will decode URL + search
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
			title: item.game.title ?? '',
			note: item.game.note ?? '',
			bgg_id: item.game.bgg_id ?? '',
			url: ov.url ?? '',
			override_price: ov.override_price ?? '',
			override_available: ov.override_available ?? '',
			_bggUrlRaw: ''
		};
		_editOriginal = { ...editForm };
	}

	function closeEdit() {
		editItem = null;
		editForm = {};
	}

	async function saveOverride() {
		editSaving = true;
		try {
			// Name, note and BGG belong to the game; price, stock and URL to the shop.
			await patchGame(editItem.game.id, {
				title: editForm.title,
				note: editForm.note || null,
				bgg_id: editForm.bgg_id === '' ? null : Number(editForm.bgg_id) || null
			});
			const listing = {};
			if (editForm.url) listing.url = editForm.url;
			if (editForm.override_price !== '')
				listing.override_price = Number(editForm.override_price) || null;
			if (editForm.override_available !== '')
				listing.override_available =
					editForm.override_available === true || editForm.override_available === 'true';
			if (Object.keys(listing).length) await setOverride(editItem.product.id, listing);
			toast.success('Saved');
			await search(true);
			closeEdit();
		} catch (e) {
			toast.error(e.message);
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

	// Load fields + stores once (independent of navigation)
	onMount(async () => {
		fields = await browseFields();
		stores = await browseStores();
	});

	const scrollKey = $derived(`catalog_scroll:${basePath}`);

	beforeNavigate(() => {
		sessionStorage.setItem(scrollKey, String(window.scrollY));
	});

	// Decode URL params and search on every navigation to this route,
	// including initial mount and same-route param changes (nav links).
	afterNavigate(async ({ type }) => {
		const savedScroll = type === 'popstate' ? Number(sessionStorage.getItem(scrollKey) || '0') : 0;
		decodeFromUrl();
		await search();
		if (savedScroll) {
			sessionStorage.removeItem(scrollKey);
			await tick();
			window.scrollTo({ top: savedScroll, behavior: 'instant' });
		}
	});
</script>

<div class="space-y-5">
	<!-- Header -->
	<div class="flex items-center justify-between gap-3">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<PageIcon class="size-6 text-primary" />
				{title}
			</h1>
			{#if subtitle}
				<p class="mt-1 text-sm text-muted-foreground">{subtitle}</p>
			{/if}
		</div>
		<div class="flex gap-2">
			{#each quickFilters as quick (quick.label)}
				{@const QuickIcon = quick.icon}
				<Button
					variant={quickFilterOn(quick.condition) ? 'default' : 'outline'}
					size="sm"
					onclick={() => toggleQuickFilter(quick.condition)}
					aria-pressed={quickFilterOn(quick.condition)}
					title={quick.title ?? quick.label}
				>
					<QuickIcon class="size-4" />
					{quick.label}
				</Button>
			{/each}
			<Button
				variant="outline"
				size="sm"
				onclick={() => {
					showSort = !showSort;
					showFilters = false;
				}}
				aria-expanded={showSort}
			>
				<ArrowUpDown class="size-4" />
				Sort
				{#if hasSorts}
					<span
						class="grid size-5 place-items-center rounded-full bg-primary text-xs text-primary-foreground"
					>
						{sorts.length}
					</span>
				{/if}
			</Button>
			<Button
				variant="outline"
				size="sm"
				onclick={() => {
					showFilters = !showFilters;
					showSort = false;
				}}
				aria-expanded={showFilters}
			>
				<SlidersHorizontal class="size-4" />
				Filters
				{#if hasFilters}
					<span
						class="grid size-5 place-items-center rounded-full bg-primary text-xs text-primary-foreground"
					>
						{filterTree.conditions.length}
					</span>
				{/if}
			</Button>
			{#if saveShelf && (hasFilters || hasSorts)}
				<Button variant="outline" size="sm" onclick={() => (saveOpen = true)}>
					<Bookmark class="size-4" /> Save shelf
				</Button>
			{/if}
		</div>
	</div>

	<!-- Sort panel -->
	{#if showSort}
		<div transition:fly={{ y: -8, duration: 180 }}>
			<SortMenu {fields} bind:sorts onapply={applyFilters} />
		</div>
	{/if}

	<!-- Filter panel -->
	{#if showFilters}
		<div transition:fly={{ y: -8, duration: 180 }}>
			<Card.Root>
				<Card.Content class="space-y-4 p-4">
					<!-- Filter builder -->
					<div class="space-y-2">
						<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Filters</p>
						{#if fields.length}
							<FilterGroup bind:group={filterTree} {fields} {stores} depth={0} />
						{/if}
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
		<p class="text-sm text-muted-foreground">
			{countLabel ? countLabel(total) : `${total} result${total === 1 ? '' : 's'}`}
		</p>
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
	{:else if shown.length === 0 && !loading}
		<div class="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
			<PageIcon class="size-10 text-muted-foreground/40" />
			<p class="font-medium">{emptyTitle}</p>
			<p class="text-sm text-muted-foreground">{emptyHint}</p>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each shown as item (item.product.id)}
				<ProductCard {item} onedit={openEdit} history={item.price_history ?? []} />
			{/each}
		</div>
		<InfiniteScroll
			hasMore={items.length < total}
			{loading}
			onload={loadMore}
			remaining={total - items.length}
		/>
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
		role="presentation"
		transition:fly={{ duration: 150 }}
		onkeydown={(e) => {
			if (e.key === 'Escape' && !editDirty) closeEdit();
		}}
		onclick={(e) => {
			if (e.target === e.currentTarget && !editDirty) closeEdit();
		}}
	>
		<div
			class="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl"
			transition:fly={{ y: 12 }}
		>
			<h2 class="mb-1 text-lg font-semibold">Edit</h2>
			<p class="mb-4 text-xs text-muted-foreground">
				Name and BGG link apply to the game everywhere. Price, stock and URL apply only to
				{editItem.product.store_id}.
			</p>
			<div class="space-y-3">
				<label class="block text-sm">
					<span class="text-muted-foreground">Name</span>
					<Input bind:value={editForm.title} placeholder={editItem.product.title} class="mt-1" />
				</label>
				<label class="block text-sm">
					<span class="text-muted-foreground">URL at {editItem.product.store_id}</span>
					<Input bind:value={editForm.url} placeholder={editItem.product.url ?? ''} class="mt-1" />
				</label>
				<label class="block text-sm">
					<span class="text-muted-foreground">BGG Link</span>

					{#if editForm.bgg_id}
						<div
							class="mt-1 flex items-center gap-2 rounded border bg-muted/50 px-2 py-1.5 text-xs"
						>
							<span class="font-mono">ID: {editForm.bgg_id}</span>
							<a
								href="https://boardgamegeek.com/boardgame/{editForm.bgg_id}"
								target="_blank"
								class="text-primary hover:underline">↗ BGG</a
							>
							<button
								onclick={() => {
									editForm.bgg_id = '';
								}}
								class="ml-auto text-muted-foreground hover:text-destructive">× clear</button
							>
						</div>
					{/if}

					<div class="mt-1 flex gap-2">
						<Input
							bind:value={editForm._bggUrlRaw}
							placeholder="Paste BGG URL to auto-fill ID"
							class="flex-1 text-sm"
							oninput={() => {
								const m = editForm._bggUrlRaw.match(
									/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i
								);
								if (m) {
									editForm.bgg_id = m[1];
									editForm._bggUrlRaw = '';
								}
							}}
						/>
						<Button
							size="sm"
							variant="outline"
							onclick={() =>
								window.open(
									`https://www.google.com/search?q=${encodeURIComponent('BGG ' + editItem.game.title)}`,
									'_blank'
								)}
						>
							Google ↗
						</Button>
					</div>
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
					<Input bind:value={editForm.note} placeholder="e.g. wait for a sale" class="mt-1" />
				</label>
			</div>
			<div class="mt-5 flex items-center gap-2">
				<Button onclick={saveOverride} disabled={editSaving}>
					{editSaving ? 'Saving…' : 'Save'}
				</Button>
				<Button variant="ghost" onclick={closeEdit}>Cancel</Button>
				{#if editItem.override}
					<Button
						variant="destructive"
						class="ml-auto"
						onclick={removeOverride}
						disabled={editSaving}
					>
						Clear corrections
					</Button>
				{/if}
			</div>
		</div>
	</div>
{/if}
