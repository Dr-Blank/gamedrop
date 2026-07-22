<script>
	import { page } from '$app/stores';
	import { fly, fade } from 'svelte/transition';
	import {
		priceHistory,
		bggGame,
		linkBgg,
		setOverride,
		clearOverride,
		hideProduct,
		unhideProduct,
		unlinkBgg,
		bggRefresh,
		patchWatchlistItem
	} from '$lib/api.js';
	import { watchlist as watchStore } from '$lib/watchlist.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import ProductImage from '$lib/components/ProductImage.svelte';
	import PriceTag from '$lib/components/PriceTag.svelte';
	import StockBadge from '$lib/components/StockBadge.svelte';
	import RatingStats from '$lib/components/RatingStats.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import {
		ArrowLeft,
		ExternalLink,
		Heart,
		Users,
		Clock,
		Baby,
		ChevronDown,
		Link2,
		Pencil,
		Eye,
		EyeOff,
		RefreshCw
	} from '@lucide/svelte';

	let productId = $derived(Number($page.params.id));
	let canGoBack = $state(false);
	let data = $state(null);
	let bgg = $state(null);
	let loading = $state(true);
	let showAllSnaps = $state(false);

	// Edit override panel
	let editOpen = $state(false);
	let saving = $state(false);
	let editForm = $state({
		title: '',
		url: '',
		override_price: '',
		override_available: null,
		note: '',
		bgg_id: null
	});
	let editBggUrlRaw = $state('');

	// BGG link/relink in hero
	let showBggInput = $state(false);
	let heroBggUrl = $state('');
	let linking = $state(false);
	let refreshing = $state(false);

	// Hide
	let hiding = $state(false);

	// Target price inline edit
	let editingTarget = $state(false);
	let targetPriceInput = $state('');

	// --- Derived ---
	const override = $derived(data?.override ?? null);
	const watchlistItem = $derived(data?.watchlist_item ?? null);

	const hasOverride = $derived.by(() => {
		if (!override) return false;
		return (
			override.title != null ||
			override.url != null ||
			override.bgg_id != null ||
			override.override_price != null ||
			override.override_available != null ||
			override.note != null
		);
	});

	const bggId = $derived(override?.bgg_id ?? data?.product?.bgg_id ?? null);
	const displayTitle = $derived(override?.title || data?.product?.title || '');
	const displayUrl = $derived(override?.url || data?.product?.url || '');

	const current = $derived(data?.history?.[0] ?? null);
	const effectivePrice = $derived(override?.override_price ?? current?.price ?? 0);
	const effectiveAvailable = $derived(override?.override_available ?? current?.available ?? false);

	const imgSrc = $derived(bgg?.image || bgg?.thumbnail || data?.product?.image_url || '');

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

	const watched = $derived(watchStore.has(productId));

	const atl = $derived.by(() => {
		if (!data?.history?.length) return null;
		return Math.min(...data.history.map((h) => h.price));
	});
	const ath = $derived.by(() => {
		if (!data?.history?.length) return null;
		return Math.max(...data.history.map((h) => h.price));
	});
	const atLowest = $derived(!!current && atl !== null && current.price <= atl);
	const daysSinceChange = $derived.by(() => {
		if (!data?.history?.length) return null;
		const h = data.history; // desc order
		const currentPrice = h[0].price;
		const changeIdx = h.findIndex((s) => s.price !== currentPrice);
		if (changeIdx <= 0) return null;
		const sinceDate = new Date(h[changeIdx - 1].recorded_at);
		return Math.floor((Date.now() - sinceDate.getTime()) / 86400000);
	});

	function fmt(n) {
		return n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
	}

	async function load() {
		loading = true;
		bgg = null;
		data = await priceHistory(productId);
		loading = false;
		const effectiveBggId = data?.override?.bgg_id ?? data?.product?.bgg_id ?? null;
		if (effectiveBggId) {
			bggGame(effectiveBggId)
				.then((g) => (bgg = g))
				.catch(() => {});
		}
	}

	function openEdit() {
		const ov = override;
		editForm = {
			title: ov?.title ?? '',
			url: ov?.url ?? '',
			override_price: ov?.override_price != null ? String(ov.override_price) : '',
			override_available: ov?.override_available ?? null,
			note: ov?.note ?? '',
			bgg_id: ov?.bgg_id ?? null
		};
		editBggUrlRaw = '';
		editOpen = true;
	}

	async function saveEdit() {
		saving = true;
		try {
			await setOverride(productId, {
				title: editForm.title || null,
				url: editForm.url || null,
				override_price: editForm.override_price ? Number(editForm.override_price) : null,
				override_available: editForm.override_available,
				note: editForm.note || null,
				bgg_id: editForm.bgg_id
			});
			toast.success('Overrides saved');
			editOpen = false;
			await load();
		} catch (e) {
			toast.error(e.message);
		} finally {
			saving = false;
		}
	}

	async function clearAllOverrides() {
		saving = true;
		try {
			await clearOverride(productId);
			toast.success('Overrides cleared');
			editOpen = false;
			await load();
		} catch (e) {
			// 404 = no override existed; treat as success
			if (e.message?.includes('404')) {
				editOpen = false;
				await load();
			} else {
				toast.error(e.message);
			}
		} finally {
			saving = false;
		}
	}

	async function toggleHide() {
		hiding = true;
		try {
			if (data.product.hidden) {
				await unhideProduct(productId);
				toast.success('Unhidden');
			} else {
				await hideProduct(productId);
				toast.success('Hidden from browse');
			}
			data.product.hidden = !data.product.hidden;
		} catch (e) {
			toast.error(e.message);
		} finally {
			hiding = false;
		}
	}

	async function linkGame(id) {
		linking = true;
		try {
			await linkBgg(id, productId);
			toast.success('Linked to BGG');
			showBggInput = false;
			heroBggUrl = '';
			await load();
		} catch (e) {
			toast.error(e.message);
		} finally {
			linking = false;
		}
	}

	async function doUnlinkBgg() {
		try {
			await unlinkBgg(productId);
			bgg = null;
			showBggInput = false;
			toast.success('BGG unlinked');
			await load();
		} catch (e) {
			toast.error(e.message);
		}
	}

	async function doRefreshBgg() {
		if (!bggId) return;
		refreshing = true;
		try {
			await bggRefresh(bggId);
			const fresh = await bggGame(bggId);
			bgg = fresh;
			toast.success('BGG data refreshed');
		} catch (e) {
			toast.error(e.message);
		} finally {
			refreshing = false;
		}
	}

	async function toggleWatch() {
		await watchStore.toggle({ product: { id: productId, title: displayTitle } });
		try {
			const fresh = await priceHistory(productId);
			if (data) data.watchlist_item = fresh.watchlist_item;
		} catch {}
	}

	async function saveTargetPrice() {
		const item = watchlistItem;
		if (!item || !targetPriceInput) {
			editingTarget = false;
			return;
		}
		try {
			await patchWatchlistItem(item.id, { target_price: Number(targetPriceInput) });
			editingTarget = false;
			toast.success('Target price updated');
			const fresh = await priceHistory(productId);
			if (data) data.watchlist_item = fresh.watchlist_item;
		} catch (e) {
			toast.error(e.message);
		}
	}

	$effect(() => {
		// Re-run whenever productId changes (SvelteKit reuses component across /prices/[id] navigations)
		void productId;
		canGoBack = window.history.length > 1;
		load();
	});
</script>

<div class="space-y-6">
	{#if canGoBack}
		<button
			onclick={() => history.back()}
			class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
		>
			<ArrowLeft class="size-4" /> Back
		</button>
	{/if}

	{#if loading}
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
		<p class="text-destructive">Product not found</p>
	{:else}
		<!-- Hero -->
		<div class="grid gap-6 md:grid-cols-[260px_1fr]">
			<div style="view-transition-name: product-{productId}">
				<Card.Root class="overflow-hidden p-0">
					<ProductImage src={imgSrc} alt={displayTitle} class="aspect-square w-full" />
				</Card.Root>
			</div>

			<div class="flex flex-col gap-4">
				<!-- Badges row + admin icons -->
				<div>
					<div class="mb-1 flex flex-wrap items-center gap-2">
						<Badge variant="outline">{data.product.store_id}</Badge>
						{#if bgg?.year}<Badge variant="outline">{bgg.year}</Badge>{/if}
						<StockBadge available={effectiveAvailable} />
						{#if data.product.hidden}
							<Badge variant="secondary" class="text-xs">hidden</Badge>
						{/if}
						{#if hasOverride}
							<Badge variant="secondary" class="text-xs">overridden</Badge>
						{/if}
						<div class="ml-auto flex items-center gap-1">
							<Button variant="ghost" size="icon" title="Edit overrides" onclick={openEdit}>
								<Pencil class="size-4" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								title={data.product.hidden ? 'Unhide' : 'Hide from browse'}
								onclick={toggleHide}
								disabled={hiding}
							>
								{#if data.product.hidden}
									<Eye class="size-4" />
								{:else}
									<EyeOff class="size-4" />
								{/if}
							</Button>
						</div>
					</div>
					<h1 class="text-3xl font-bold tracking-tight">{displayTitle}</h1>
					{#if bgg}<div class="mt-2"><RatingStats {bgg} /></div>{/if}
				</div>

				<!-- Price + stats -->
				{#if current}
					<div class="space-y-1">
						<div class="flex flex-wrap items-end gap-3">
							<PriceTag price={effectivePrice} compareAt={current.compare_at_price} size="lg" />
							{#if atLowest}
								<span
									class="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400"
								>
									At lowest
								</span>
							{/if}
						</div>
						{#if atl !== null && ath !== null && atl !== ath}
							<p class="text-xs text-muted-foreground">ATL ₹{fmt(atl)} · ATH ₹{fmt(ath)}</p>
						{/if}
						{#if daysSinceChange !== null}
							<p class="text-xs text-muted-foreground">
								Unchanged {daysSinceChange}
								{daysSinceChange === 1 ? 'day' : 'days'}
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
					<!-- Watch + target price -->
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
									class="text-sm text-muted-foreground hover:text-foreground"
								>
									✕
								</button>
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
										? '₹' + fmt(watchlistItem.target_price)
										: 'any drop'}
								</button>
							{/if}
						{/if}
					</div>

					<!-- Store + BGG buttons -->
					<div class="flex flex-wrap gap-2">
						{#if displayUrl}
							<Button variant="outline" href={displayUrl} target="_blank">
								<ExternalLink class="size-4" /> View on store
							</Button>
						{/if}
						{#if bgg?.bgg_url}
							<Button variant="outline" href={bgg.bgg_url} target="_blank">BGG ↗</Button>
						{:else if bggId}
							<Button
								variant="outline"
								href="https://boardgamegeek.com/boardgame/{bggId}"
								target="_blank"
							>
								BGG ↗
							</Button>
						{/if}
						{#if bggId}
							<Button
								variant="ghost"
								size="sm"
								onclick={() => {
									showBggInput = !showBggInput;
									heroBggUrl = '';
								}}
							>
								Re-link
							</Button>
							<Button variant="ghost" size="sm" onclick={doRefreshBgg} disabled={refreshing}>
								<RefreshCw class="size-4 {refreshing ? 'animate-spin' : ''}" />
								{refreshing ? 'Refreshing…' : 'Refresh BGG'}
							</Button>
						{:else}
							<Button variant="ghost" size="sm" onclick={() => (showBggInput = !showBggInput)}>
								<Link2 class="size-4" /> Link BGG
							</Button>
						{/if}
					</div>

					<!-- BGG URL paste input (hero) -->
					{#if showBggInput}
						<div class="flex gap-2" transition:fly={{ y: -4, duration: 150 }}>
							<input
								bind:value={heroBggUrl}
								placeholder="Paste BGG URL…"
								class="h-9 flex-1 rounded-lg border bg-background px-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
								oninput={() => {
									const m = heroBggUrl.match(
										/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i
									);
									if (m) linkGame(Number(m[1]));
								}}
								disabled={linking}
							/>
							<Button
								variant="outline"
								onclick={() =>
									window.open(
										`https://www.google.com/search?q=${encodeURIComponent('BGG ' + displayTitle)}`,
										'_blank'
									)}
							>
								Google ↗
							</Button>
							{#if bggId}
								<Button
									variant="ghost"
									size="sm"
									class="text-destructive hover:bg-destructive/10 hover:text-destructive"
									onclick={doUnlinkBgg}
								>
									Unlink
								</Button>
							{/if}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Override edit panel -->
		{#if editOpen}
			<div transition:fly={{ y: 8, duration: 200 }}>
				<Card.Root>
					<Card.Header class="flex-row items-center justify-between pb-3">
						<Card.Title class="flex items-center gap-2 text-base">
							<Pencil class="size-4" /> Edit overrides
						</Card.Title>
						<button
							onclick={() => (editOpen = false)}
							class="text-muted-foreground transition-colors hover:text-foreground"
						>
							✕
						</button>
					</Card.Header>
					<Card.Content class="space-y-4">
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="space-y-1">
								<label for="ov-title" class="text-xs font-medium text-muted-foreground">Title</label
								>
								<Input id="ov-title" bind:value={editForm.title} placeholder={data.product.title} />
							</div>
							<div class="space-y-1">
								<label for="ov-url" class="text-xs font-medium text-muted-foreground">URL</label>
								<Input
									id="ov-url"
									bind:value={editForm.url}
									placeholder={data.product.url ?? 'Product URL'}
								/>
							</div>
							<div class="space-y-1">
								<label for="ov-price" class="text-xs font-medium text-muted-foreground"
									>Price override (₹)</label
								>
								<Input
									id="ov-price"
									type="number"
									bind:value={editForm.override_price}
									placeholder="Leave blank to use scraped price"
								/>
							</div>
							<div class="space-y-1">
								<label for="ov-stock" class="text-xs font-medium text-muted-foreground"
									>Stock override</label
								>
								<select
									id="ov-stock"
									bind:value={editForm.override_available}
									class="h-9 w-full rounded-md border bg-background px-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
								>
									<option value={null}>Use scraped stock</option>
									<option value={true}>In stock</option>
									<option value={false}>Out of stock</option>
								</select>
							</div>
							<div class="space-y-1 sm:col-span-2">
								<label for="ov-note" class="text-xs font-medium text-muted-foreground">Note</label>
								<textarea
									id="ov-note"
									bind:value={editForm.note}
									placeholder="Internal note…"
									class="min-h-[4rem] w-full rounded-md border bg-background px-3 py-2 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
									rows="2"
								></textarea>
							</div>
							<div class="space-y-1 sm:col-span-2">
								<label for="ov-bgg" class="text-xs font-medium text-muted-foreground"
									>BGG link</label
								>
								{#if editForm.bgg_id}
									<div class="flex items-center gap-2">
										<span class="rounded-md border bg-muted px-3 py-1.5 font-mono text-sm">
											BGG #{editForm.bgg_id}
										</span>
										<Button
											variant="outline"
											size="sm"
											href="https://boardgamegeek.com/boardgame/{editForm.bgg_id}"
											target="_blank"
										>
											View ↗
										</Button>
										<Button
											variant="ghost"
											size="sm"
											onclick={() => {
												editForm.bgg_id = null;
												editBggUrlRaw = '';
											}}
										>
											Clear
										</Button>
									</div>
								{:else}
									<div class="flex gap-2">
										<Input
											id="ov-bgg"
											bind:value={editBggUrlRaw}
											placeholder="Paste BGG URL to link…"
											oninput={() => {
												const m = editBggUrlRaw.match(
													/boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i
												);
												if (m) editForm.bgg_id = Number(m[1]);
											}}
										/>
										<Button
											variant="outline"
											onclick={() =>
												window.open(
													`https://www.google.com/search?q=${encodeURIComponent(
														'BGG ' + (editForm.title || data.product.title)
													)}`,
													'_blank'
												)}
										>
											Google ↗
										</Button>
									</div>
								{/if}
							</div>
						</div>

						<div class="flex flex-wrap gap-2 border-t pt-4">
							<Button onclick={saveEdit} disabled={saving}>
								{saving ? 'Saving…' : 'Save'}
							</Button>
							{#if hasOverride}
								<Button
									variant="outline"
									onclick={clearAllOverrides}
									disabled={saving}
									class="text-destructive hover:bg-destructive/10 hover:text-destructive"
								>
									Clear all overrides
								</Button>
							{/if}
							<Button variant="ghost" onclick={() => (editOpen = false)} disabled={saving}>
								Cancel
							</Button>
						</div>
					</Card.Content>
				</Card.Root>
			</div>
		{/if}

		<!-- Price chart -->
		{#if data.history.length > 1}
			<Card.Root>
				<Card.Header><Card.Title>Price history</Card.Title></Card.Header>
				<Card.Content>
					<PriceChart history={data.history} />
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

		<!-- About -->
		{#if bgg?.description}
			<Card.Root>
				<Card.Header><Card.Title>About</Card.Title></Card.Header>
				<Card.Content class="text-sm leading-relaxed text-muted-foreground">
					{bgg.description}{bgg.description.length >= 500 ? '…' : ''}
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Price snapshots -->
		<Card.Root>
			<Card.Header class="flex-row items-center justify-between">
				<Card.Title>Price snapshots</Card.Title>
				<span class="text-xs text-muted-foreground">{data.history.length} records</span>
			</Card.Header>
			<Card.Content>
				<div class="overflow-hidden rounded-lg border">
					<table class="w-full text-sm">
						<thead class="bg-muted/50 text-muted-foreground">
							<tr>
								<th class="px-3 py-2 text-left font-medium">Date</th>
								<th class="px-3 py-2 text-right font-medium">Price</th>
								<th class="px-3 py-2 text-center font-medium">Stock</th>
							</tr>
						</thead>
						<tbody class="divide-y">
							{#each showAllSnaps ? data.history : data.history.slice(0, 8) as snap}
								<tr class="transition-colors hover:bg-muted/30">
									<td class="px-3 py-2 text-muted-foreground">
										{new Date(snap.recorded_at).toLocaleString('en-IN', {
											day: 'numeric',
											month: 'short',
											year: 'numeric',
											hour: '2-digit',
											minute: '2-digit'
										})}
									</td>
									<td class="px-3 py-2 text-right font-semibold tabular-nums">
										₹{snap.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
									</td>
									<td class="px-3 py-2 text-center">
										{#if snap.available}
											<span class="text-green-600 dark:text-green-400">●</span>
										{:else}
											<span class="text-destructive">●</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if data.history.length > 8}
					<button
						onclick={() => (showAllSnaps = !showAllSnaps)}
						class="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
					>
						<ChevronDown class="size-4 transition-transform {showAllSnaps ? 'rotate-180' : ''}" />
						{showAllSnaps ? 'Show less' : `Show all ${data.history.length}`}
					</button>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
