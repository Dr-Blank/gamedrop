<script>
	import { page } from '$app/stores';
	import { goto, replaceState } from '$app/navigation';
	import { fly } from 'svelte/transition';
	import {
		getGame,
		patchGame,
		listingDetail,
		bggGame,
		linkBgg,
		unlinkBgg,
		bggRefresh,
		setOverride,
		clearOverride,
		hideProduct,
		unhideProduct,
		unmergeProduct,
		patchWatchlistItem
	} from '$lib/api.js';
	import { watchlist as watchStore } from '$lib/watchlist.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import PriceTag from '$lib/components/PriceTag.svelte';
	import StockBadge from '$lib/components/StockBadge.svelte';
	import RatingStats from '$lib/components/RatingStats.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import GameGallery from '$lib/components/GameGallery.svelte';
	import StoreOffers from '$lib/components/StoreOffers.svelte';
	import StoreFilter from '$lib/components/StoreFilter.svelte';
	import PriceTimeline from '$lib/components/PriceTimeline.svelte';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import MergeSuggestions from '$lib/components/MergeSuggestions.svelte';
	import { gamePricing, inr } from '$lib/gamePricing.js';
	import { lastPriceChange } from '$lib/priceChange.js';
	import { buildTimeline } from '$lib/priceTimeline.js';
	import {
		ArrowLeft,
		ExternalLink,
		Heart,
		Users,
		Clock,
		Baby,
		Link2,
		Pencil,
		Eye,
		EyeOff,
		RefreshCw,
		Store,
		Loader
	} from '@lucide/svelte';

	const gameId = $derived(Number($page.params.id));

	let data = $state(null);
	let bgg = $state(null);
	let canGoBack = $state(false);
	// Skeletons only on the first paint of a game. Switching shop or refetching
	// keeps the rendered page and shows a small spinner instead — the whole point
	// of tabs is that nothing else on the page changes.
	let firstLoad = $state(true);
	let refreshing = $state(false);

	let selectedId = $state(/** @type {number|null} */ (null));
	let listing = $state(null);
	let listingLoading = $state(false);
	let busy = $state(false);

	// Edit panels
	let editGameOpen = $state(false);
	let gameForm = $state({ title: '', note: '' });
	let editListingOpen = $state(false);
	let listingForm = $state({ url: '', override_price: '', override_available: null });
	let saving = $state(false);

	let showBggInput = $state(false);
	let bggUrl = $state('');
	let linking = $state(false);
	let bggRefreshing = $state(false);

	let editingTarget = $state(false);
	let targetPriceInput = $state('');

	// --- Derived ---
	const game = $derived(data?.game ?? null);
	const offers = $derived(data?.offers ?? []);
	const pricing = $derived(gamePricing(data));
	const watchlistItem = $derived(data?.watchlist_item ?? null);
	const watched = $derived(watchStore.has(gameId));
	const multiStore = $derived(offers.length > 1);

	const selected = $derived(offers.find((o) => o.product_id === selectedId) ?? offers[0] ?? null);
	const override = $derived(listing?.override ?? null);
	const history = $derived(listing?.history ?? []);

	const imgSrc = $derived(bgg?.image || bgg?.thumbnail || selected?.image_url || '');
	const bestBuyable = $derived(data?.cheapest_in_stock ?? null);

	const players = $derived(
		bgg?.min_players
			? bgg.min_players === bgg.max_players
				? `${bgg.min_players}`
				: `${bgg.min_players}–${bgg.max_players}`
			: null
	);
	const playtime = $derived(
		bgg?.min_playtime
			? bgg.min_playtime === bgg.max_playtime
				? `${bgg.min_playtime} min`
				: `${bgg.min_playtime}–${bgg.max_playtime} min`
			: null
	);

	const atl = $derived(history.length ? Math.min(...history.map((h) => h.price)) : null);
	const ath = $derived(history.length ? Math.max(...history.map((h) => h.price)) : null);
	const atLowest = $derived(
		!!selected && atl !== null && selected.price != null && selected.price <= atl
	);
	const priceChange = $derived(lastPriceChange(history));

	const chartSeries = $derived(
		(data?.series ?? []).map((s) => ({
			label: s.store_id,
			store_id: s.store_id,
			product_id: s.product_id,
			history: s.history
		}))
	);
	// Shops the reader switched off: the chart and the timeline share one filter.
	let hiddenStores = $state(new Set());
	const visibleSeries = $derived(chartSeries.filter((s) => !hiddenStores.has(s.store_id)));
	const chartPoints = $derived(visibleSeries.reduce((n, s) => n + (s.history?.length ?? 0), 0));
	const timeline = $derived(buildTimeline(chartSeries, { hidden: hiddenStores }));

	/** @param {string} storeId */
	function toggleStore(storeId) {
		const next = new Set(hiddenStores);
		if (next.has(storeId)) next.delete(storeId);
		else if (visibleSeries.length > 1) next.add(storeId);
		hiddenStores = next;
	}

	async function loadGame({ keepSelection = false } = {}) {
		refreshing = true;
		try {
			const fresh = await getGame(gameId);
			data = fresh;
			const wanted = keepSelection ? selectedId : pickStore(fresh);
			const exists = fresh.offers.some((o) => o.product_id === wanted);
			await selectListing(exists ? wanted : (fresh.offers[0]?.product_id ?? null), {
				updateUrl: false
			});
		} catch (e) {
			toast.error(e.message);
			data = null;
		} finally {
			refreshing = false;
			firstLoad = false;
		}
	}

	/** ?store= picks the shop to open on, so a card links straight to its own. */
	function pickStore(payload) {
		const wanted = $page.url.searchParams.get('store');
		const match = payload.offers.find((o) => o.store_id === wanted);
		return (match ?? payload.cheapest_in_stock ?? payload.cheapest ?? payload.offers[0])
			?.product_id;
	}

	async function selectListing(productId, { updateUrl = true } = {}) {
		if (productId == null) {
			listing = null;
			selectedId = null;
			return;
		}
		selectedId = productId;
		listingLoading = true;
		try {
			listing = await listingDetail(gameId, productId);
		} catch (e) {
			toast.error(e.message);
			listing = null;
		} finally {
			listingLoading = false;
		}
		if (updateUrl) {
			// Shallow update: the address bar follows the tab without re-running
			// load, so switching shops never re-renders the page.
			const url = new URL($page.url);
			const offer = offers.find((o) => o.product_id === productId);
			if (offer) url.searchParams.set('store', offer.store_id);
			replaceState(url, {});
		}
	}

	/** Merging can absorb this game into another, which retires this URL. */
	async function afterMerge(payload) {
		const survivor = payload?.game?.id;
		if (survivor && survivor !== gameId) {
			const store = payload.offers?.find((o) => o.product_id === selectedId)?.store_id;
			await goto(`/games/${survivor}${store ? `?store=${encodeURIComponent(store)}` : ''}`, {
				replaceState: true
			});
			return;
		}
		await loadGame({ keepSelection: true });
	}

	async function toggleWatch() {
		await watchStore.toggle({ game, product: { id: selected?.product_id, game_id: gameId } });
		await loadGame({ keepSelection: true });
	}

	async function saveTargetPrice() {
		if (!watchlistItem || !targetPriceInput) {
			editingTarget = false;
			return;
		}
		try {
			await patchWatchlistItem(watchlistItem.id, { target_price: Number(targetPriceInput) });
			editingTarget = false;
			toast.success('Target price updated');
			await loadGame({ keepSelection: true });
		} catch (e) {
			toast.error(e.message);
		}
	}

	function openGameEdit() {
		gameForm = { title: game?.title ?? '', note: game?.note ?? '' };
		editGameOpen = true;
	}

	async function saveGame() {
		saving = true;
		try {
			data = await patchGame(gameId, { title: gameForm.title, note: gameForm.note });
			toast.success('Game updated');
			editGameOpen = false;
		} catch (e) {
			toast.error(e.message);
		} finally {
			saving = false;
		}
	}

	function openListingEdit() {
		listingForm = {
			url: override?.url ?? '',
			override_price: override?.override_price != null ? String(override.override_price) : '',
			override_available: override?.override_available ?? null
		};
		editListingOpen = true;
	}

	async function saveListing() {
		saving = true;
		try {
			await setOverride(selectedId, {
				url: listingForm.url || null,
				override_price: listingForm.override_price ? Number(listingForm.override_price) : null,
				override_available: listingForm.override_available
			});
			toast.success('Listing corrections saved');
			editListingOpen = false;
			await loadGame({ keepSelection: true });
			await selectListing(selectedId, { updateUrl: false });
		} catch (e) {
			toast.error(e.message);
		} finally {
			saving = false;
		}
	}

	async function clearListingOverride() {
		saving = true;
		try {
			await clearOverride(selectedId);
			editListingOpen = false;
			await loadGame({ keepSelection: true });
		} catch (e) {
			if (!e.message?.includes('404')) toast.error(e.message);
			editListingOpen = false;
		} finally {
			saving = false;
		}
	}

	async function toggleHide() {
		busy = true;
		try {
			if (game.hidden) {
				await unhideProduct(selectedId);
				toast.success('Unhidden');
			} else {
				await hideProduct(selectedId);
				toast.success('Hidden from browse');
			}
			await loadGame({ keepSelection: true });
		} catch (e) {
			toast.error(e.message);
		} finally {
			busy = false;
		}
	}

	async function splitOff(productId) {
		busy = true;
		try {
			await unmergeProduct(productId);
			toast.success('Unmerged');
			await loadGame({ keepSelection: productId !== selectedId });
		} catch (e) {
			toast.error(e.message);
		} finally {
			busy = false;
		}
	}

	async function linkGame(id) {
		linking = true;
		try {
			await linkBgg(id, selectedId);
			showBggInput = false;
			bggUrl = '';
			toast.success('Linked to BGG');
			await loadGame({ keepSelection: true });
		} catch (e) {
			toast.error(e.message);
		} finally {
			linking = false;
		}
	}

	async function doUnlinkBgg() {
		try {
			await unlinkBgg(selectedId);
			bgg = null;
			showBggInput = false;
			toast.success('BGG unlinked');
			await loadGame({ keepSelection: true });
		} catch (e) {
			toast.error(e.message);
		}
	}

	async function doRefreshBgg() {
		if (!game?.bgg_id) return;
		bggRefreshing = true;
		try {
			await bggRefresh(game.bgg_id);
			bgg = await bggGame(game.bgg_id);
			toast.success('BGG data refreshed');
		} catch (e) {
			toast.error(e.message);
		} finally {
			bggRefreshing = false;
		}
	}

	// Game-level load: only when the game in the URL changes.
	$effect(() => {
		const id = gameId;
		firstLoad = true;
		bgg = null;
		canGoBack = window.history.length > 1;
		loadGame();
		return () => {
			void id;
		};
	});

	// BGG detail follows the game's link, independently of the shop tab.
	$effect(() => {
		const bggId = game?.bgg_id ?? null;
		if (!bggId) {
			bgg = null;
			return;
		}
		bggGame(bggId)
			.then((g) => (bgg = g))
			.catch(() => {});
	});
</script>

<div class="space-y-6">
	{#if canGoBack}
		<button
			onclick={() => window.history.back()}
			class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
		>
			<ArrowLeft class="size-4" /> Back
		</button>
	{/if}

	{#if firstLoad}
		<div class="grid gap-6 md:grid-cols-[260px_1fr]">
			<Skeleton class="aspect-square w-full rounded-xl" />
			<div class="space-y-3">
				<Skeleton class="h-8 w-2/3" />
				<Skeleton class="h-5 w-40" />
				<Skeleton class="h-20 w-full" />
			</div>
		</div>
		<Skeleton class="h-72 w-full rounded-xl" />
	{:else if !data}
		<p class="text-destructive">Game not found</p>
	{:else}
		<!-- Hero -->
		<div class="grid gap-6 md:grid-cols-[260px_1fr]">
			<div style="view-transition-name: game-{gameId}">
				<Card.Root class="overflow-hidden p-0">
					<GameGallery images={data.images} primary={imgSrc} alt={game.title} />
				</Card.Root>
			</div>

			<div class="flex flex-col gap-4">
				<div>
					<div class="mb-1 flex flex-wrap items-center gap-2">
						{#if multiStore}
							<Badge variant="outline" class="gap-1">
								<Store class="size-3" />
								{data.store_ids.length} stores
							</Badge>
						{:else}
							<Badge variant="outline">{selected?.store_id}</Badge>
						{/if}
						{#if bgg?.year}<Badge variant="outline">{bgg.year}</Badge>{/if}
						<StockBadge available={selected?.available ?? false} />
						{#if game.hidden}<Badge variant="secondary" class="text-xs">hidden</Badge>{/if}
						{#if override}<Badge variant="secondary" class="text-xs">corrected</Badge>{/if}
						{#if refreshing}
							<Loader class="size-3.5 animate-spin text-muted-foreground" />
						{/if}
						<div class="ml-auto flex items-center gap-1">
							<Button variant="ghost" size="icon" title="Rename / note" onclick={openGameEdit}>
								<Pencil class="size-4" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								title={game.hidden ? 'Unhide' : 'Hide from browse'}
								onclick={toggleHide}
								disabled={busy}
							>
								{#if game.hidden}<Eye class="size-4" />{:else}<EyeOff class="size-4" />{/if}
							</Button>
						</div>
					</div>
					<h1 class="text-3xl font-bold tracking-tight">{game.title}</h1>
					{#if bgg}<div class="mt-2"><RatingStats {bgg} /></div>{/if}
					{#if game.note}
						<p class="mt-1 text-sm text-muted-foreground italic">{game.note}</p>
					{/if}
				</div>

				<!-- Shop tabs: switching one only swaps the panel below, never the page -->
				{#if multiStore}
					<div class="flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1">
						{#each offers as offer (offer.product_id)}
							<button
								onclick={() => selectListing(offer.product_id)}
								class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {offer.product_id ===
								selectedId
									? 'bg-background text-foreground shadow-sm'
									: 'text-muted-foreground hover:text-foreground'}"
								style="box-shadow: inset 0 -2px 0 0 {tint(
									storeColors.of(offer.store_id),
									offer.product_id === selectedId ? 0.9 : 0.25
								)}"
								aria-current={offer.product_id === selectedId}
							>
								{offer.store_id}
								<span
									class="ml-1 tabular-nums {offer.available
										? ''
										: 'text-muted-foreground/70 line-through'}"
								>
									{inr(offer.price)}
								</span>
								{#if bestBuyable?.product_id === offer.product_id}
									<span class="ml-1 text-green-600 dark:text-green-400">●</span>
								{/if}
							</button>
						{/each}
					</div>
				{/if}

				<!-- Price -->
				{#if selected}
					<div class="space-y-1">
						<div class="flex flex-wrap items-end gap-3">
							<PriceTag price={selected.price} size="lg" />
							{#if atLowest}
								<span
									class="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400"
								>
									At lowest
								</span>
							{/if}
						</div>
						{#if pricing?.blocked && pricing.blocked.product_id === selected.product_id}
							<p class="text-xs text-muted-foreground">
								Out of stock here — buyable for {inr(pricing.primary.price)} at
								<button
									class="font-medium hover:underline"
									onclick={() => selectListing(pricing.primary.product_id)}
								>
									{pricing.primary.store_id}
								</button>
							</p>
						{:else if multiStore && bestBuyable?.product_id === selected.product_id}
							<p class="text-xs text-green-600 dark:text-green-400">
								Cheapest in-stock price across {data.store_ids.length} stores
							</p>
						{:else if multiStore && !bestBuyable}
							<p class="text-xs text-rose-500">Out of stock at every store</p>
						{/if}
						{#if atl !== null && ath !== null && atl !== ath}
							<p class="text-xs text-muted-foreground">
								ATL {inr(atl)} · ATH {inr(ath)} at {selected.store_id}
							</p>
						{/if}
						{#if priceChange}
							<p class="text-xs text-muted-foreground">
								{priceChange.changed
									? `Price changed ${priceChange.label} ago`
									: `Price unchanged for ${priceChange.label}`}
							</p>
						{/if}
					</div>
				{/if}

				<!-- Quick facts -->
				{#if bgg && (players || playtime || bgg.min_age)}
					<div class="flex flex-wrap gap-x-6 gap-y-2 text-sm">
						{#if players}
							<span class="inline-flex items-center gap-1.5">
								<Users class="size-4 text-muted-foreground" />
								{players} players
							</span>
						{/if}
						{#if playtime}
							<span class="inline-flex items-center gap-1.5">
								<Clock class="size-4 text-muted-foreground" />
								{playtime}
							</span>
						{/if}
						{#if bgg.min_age}
							<span class="inline-flex items-center gap-1.5">
								<Baby class="size-4 text-muted-foreground" />
								{bgg.min_age}+
							</span>
						{/if}
					</div>
				{/if}

				<!-- Actions -->
				<div class="mt-auto space-y-3">
					<div class="flex flex-wrap items-center gap-2">
						<Button onclick={toggleWatch} variant={watched ? 'secondary' : 'default'}>
							<Heart class="size-4" fill={watched ? 'currentColor' : 'none'} />
							{watched ? 'Watching' : 'Watch'}
						</Button>
						{#if watched}
							{#if editingTarget}
								<input
									type="number"
									bind:value={targetPriceInput}
									placeholder="Any drop"
									class="h-8 w-28 rounded-md border bg-background px-2 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
								/>
								<Button size="sm" onclick={saveTargetPrice}>Set</Button>
								<button
									onclick={() => (editingTarget = false)}
									class="text-sm text-muted-foreground hover:text-foreground">✕</button
								>
							{:else}
								<button
									onclick={() => {
										targetPriceInput = watchlistItem?.target_price
											? String(watchlistItem.target_price)
											: '';
										editingTarget = true;
									}}
									class="text-xs text-muted-foreground hover:underline"
								>
									target: {watchlistItem?.target_price
										? inr(watchlistItem.target_price)
										: 'any drop'}
								</button>
							{/if}
						{/if}
					</div>

					<div class="flex flex-wrap gap-2">
						{#if selected?.url}
							<Button variant="outline" href={selected.url} target="_blank">
								<ExternalLink class="size-4" /> View at {selected.store_id}
							</Button>
						{/if}
						{#if bgg?.bgg_url || game.bgg_id}
							<Button
								variant="outline"
								href={bgg?.bgg_url || `https://boardgamegeek.com/boardgame/${game.bgg_id}`}
								target="_blank">BGG ↗</Button
							>
						{/if}
						{#if game.bgg_id}
							<Button
								variant="ghost"
								size="sm"
								onclick={() => {
									showBggInput = !showBggInput;
									bggUrl = '';
								}}>Re-link</Button
							>
							<Button variant="ghost" size="sm" onclick={doRefreshBgg} disabled={bggRefreshing}>
								<RefreshCw class="size-4 {bggRefreshing ? 'animate-spin' : ''}" />
								{bggRefreshing ? 'Refreshing…' : 'Refresh BGG'}
							</Button>
						{:else}
							<Button variant="ghost" size="sm" onclick={() => (showBggInput = !showBggInput)}>
								<Link2 class="size-4" /> Link BGG
							</Button>
						{/if}
						<Button variant="ghost" size="sm" onclick={openListingEdit}>
							Correct {selected?.store_id} listing
						</Button>
					</div>

					{#if showBggInput}
						<div class="flex gap-2" transition:fly={{ y: -4, duration: 150 }}>
							<input
								bind:value={bggUrl}
								placeholder="Paste BGG URL…"
								class="h-9 flex-1 rounded-lg border bg-background px-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
								oninput={() => {
									const m = bggUrl.match(/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i);
									if (m) linkGame(Number(m[1]));
								}}
								disabled={linking}
							/>
							<Button
								variant="outline"
								onclick={() =>
									window.open(
										`https://www.google.com/search?q=${encodeURIComponent('BGG ' + game.title)}`,
										'_blank'
									)}>Google ↗</Button
							>
							{#if game.bgg_id}
								<Button
									variant="ghost"
									size="sm"
									class="text-destructive hover:bg-destructive/10 hover:text-destructive"
									onclick={doUnlinkBgg}>Unlink</Button
								>
							{/if}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Game edit -->
		{#if editGameOpen}
			<div transition:fly={{ y: 8, duration: 200 }}>
				<Card.Root>
					<Card.Header class="flex-row items-center justify-between pb-3">
						<Card.Title class="flex items-center gap-2 text-base">
							<Pencil class="size-4" /> Edit game
						</Card.Title>
						<button
							onclick={() => (editGameOpen = false)}
							class="text-muted-foreground transition-colors hover:text-foreground">✕</button
						>
					</Card.Header>
					<Card.Content class="space-y-4">
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="space-y-1">
								<label for="game-title" class="text-xs font-medium text-muted-foreground">
									Name
								</label>
								<Input id="game-title" bind:value={gameForm.title} />
								<p class="text-[0.7rem] text-muted-foreground">
									Shown everywhere, for every shop selling it.
								</p>
							</div>
							<div class="space-y-1">
								<label for="game-note" class="text-xs font-medium text-muted-foreground">
									Note
								</label>
								<Input id="game-note" bind:value={gameForm.note} placeholder="Internal note…" />
							</div>
						</div>
						<div class="flex gap-2 border-t pt-4">
							<Button onclick={saveGame} disabled={saving}>
								{saving ? 'Saving…' : 'Save'}
							</Button>
							<Button variant="ghost" onclick={() => (editGameOpen = false)} disabled={saving}>
								Cancel
							</Button>
						</div>
					</Card.Content>
				</Card.Root>
			</div>
		{/if}

		<!-- Listing corrections -->
		{#if editListingOpen}
			<div transition:fly={{ y: 8, duration: 200 }}>
				<Card.Root>
					<Card.Header class="flex-row items-center justify-between pb-3">
						<Card.Title class="text-base">Correct {selected?.store_id} listing</Card.Title>
						<button
							onclick={() => (editListingOpen = false)}
							class="text-muted-foreground transition-colors hover:text-foreground">✕</button
						>
					</Card.Header>
					<Card.Content class="space-y-4">
						<div class="grid gap-4 sm:grid-cols-3">
							<div class="space-y-1">
								<label for="ov-url" class="text-xs font-medium text-muted-foreground">URL</label>
								<Input
									id="ov-url"
									bind:value={listingForm.url}
									placeholder={selected?.url ?? 'Listing URL'}
								/>
							</div>
							<div class="space-y-1">
								<label for="ov-price" class="text-xs font-medium text-muted-foreground">
									Price override (₹)
								</label>
								<Input
									id="ov-price"
									type="number"
									bind:value={listingForm.override_price}
									placeholder="Scraped price"
								/>
							</div>
							<div class="space-y-1">
								<label for="ov-stock" class="text-xs font-medium text-muted-foreground">
									Stock override
								</label>
								<select
									id="ov-stock"
									bind:value={listingForm.override_available}
									class="h-9 w-full rounded-md border bg-background px-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
								>
									<option value={null}>Use scraped stock</option>
									<option value={true}>In stock</option>
									<option value={false}>Out of stock</option>
								</select>
							</div>
						</div>
						<div class="flex flex-wrap gap-2 border-t pt-4">
							<Button onclick={saveListing} disabled={saving}>
								{saving ? 'Saving…' : 'Save'}
							</Button>
							{#if override}
								<Button
									variant="outline"
									onclick={clearListingOverride}
									disabled={saving}
									class="text-destructive hover:bg-destructive/10 hover:text-destructive"
								>
									Clear corrections
								</Button>
							{/if}
							<Button variant="ghost" onclick={() => (editListingOpen = false)} disabled={saving}>
								Cancel
							</Button>
						</div>
					</Card.Content>
				</Card.Root>
			</div>
		{/if}

		<div class="grid gap-6 lg:grid-cols-[1fr_320px]">
			<div class="min-w-0 space-y-6">
				<!-- Price chart: one line per shop once merged -->
				{#if chartPoints > 1}
					<Card.Root>
						<Card.Header>
							<Card.Title>
								Price history{multiStore ? ` · ${data.store_ids.length} stores` : ''}
							</Card.Title>
						</Card.Header>
						<Card.Content class="space-y-4">
							<PriceChart series={visibleSeries} />
							{#if multiStore}
								<StoreFilter
									stores={chartSeries.map((s) => s.store_id)}
									hidden={hiddenStores}
									ontoggle={toggleStore}
								/>
							{/if}
						</Card.Content>
					</Card.Root>
				{:else}
					<Card.Root>
						<Card.Content class="p-6 text-sm text-muted-foreground">
							Not enough price history yet — need at least 2 data points. Check back after the next
							sync.
						</Card.Content>
					</Card.Root>
				{/if}

				{#if bgg?.description}
					<Card.Root>
						<Card.Header><Card.Title>About</Card.Title></Card.Header>
						<Card.Content class="text-sm leading-relaxed text-muted-foreground">
							{bgg.description}{bgg.description.length >= 500 ? '…' : ''}
						</Card.Content>
					</Card.Root>
				{/if}

				<!-- Every shop's changes, newest first -->
				<Card.Root>
					<Card.Header class="flex-row items-center justify-between">
						<Card.Title>Price timeline</Card.Title>
						<span class="text-xs text-muted-foreground">
							{listingLoading ? 'loading…' : `${timeline.length} changes`}
						</span>
					</Card.Header>
					<Card.Content class="space-y-4">
						{#if multiStore}
							<StoreFilter
								stores={chartSeries.map((s) => s.store_id)}
								hidden={hiddenStores}
								ontoggle={toggleStore}
							/>
						{/if}
						<PriceTimeline events={timeline} {multiStore} />
					</Card.Content>
				</Card.Root>
			</div>

			<aside class="space-y-6">
				{#if multiStore}
					<Card.Root>
						<Card.Header class="pb-3">
							<Card.Title class="flex items-center gap-2 text-base">
								<Store class="size-4" /> Across stores
							</Card.Title>
						</Card.Header>
						<Card.Content>
							<StoreOffers
								compare={data}
								currentProductId={selectedId}
								onselect={(id) => selectListing(id)}
								onunmerge={busy ? null : splitOff}
							/>
						</Card.Content>
					</Card.Root>
				{/if}

				<MergeSuggestions productId={selectedId} onmerged={afterMerge} />
			</aside>
		</div>
	{/if}
</div>
