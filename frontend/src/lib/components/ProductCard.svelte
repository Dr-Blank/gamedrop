<script>
	import { goto } from '$app/navigation';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import ProductImage from './ProductImage.svelte';
	import PriceTag from './PriceTag.svelte';
	import StockBadge from './StockBadge.svelte';
	import RatingStats from './RatingStats.svelte';
	import Sparkline from './Sparkline.svelte';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { hidden } from '$lib/hidden.svelte.js';
	import { gamePricing, inr } from '$lib/gamePricing.js';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import {
		Heart,
		Pencil,
		ExternalLink,
		Trash2,
		Target,
		TrendingDown,
		TrendingUp,
		EyeOff,
		RotateCcw,
		Store,
		XCircle
	} from '@lucide/svelte';

	let {
		item,
		history = /** @type {Array<{price:number}>} */ ([]),
		variant = 'browse', // 'browse' | 'watchlist' | 'hidden'
		target = /** @type {number|null} */ (null),
		onremove = /** @type {(()=>void)|null} */ (null),
		onedit = /** @type {((item:any)=>void)|null} */ (null),
		ontarget = /** @type {(()=>void)|null} */ (null)
	} = $props();

	const gameId = $derived(item.game?.id ?? item.product.game_id);
	const watched = $derived(watchlist.has(gameId));
	const isHidden = $derived(hidden.has(gameId));

	// The name is the game's; the shop's own title stays on the listing.
	const title = $derived(item.game?.title || item.product.title);
	const ownPrice = $derived(
		item.override?.override_price != null
			? item.override.override_price
			: (item.latest_price?.price ?? null)
	);
	const ownAvailable = $derived(
		item.override?.override_available != null
			? item.override.override_available
			: (item.latest_price?.available ?? false)
	);

	// A game sold by several shops quotes the cheapest price that can actually
	// be bought, with a cheaper out-of-stock offer flagged below it.
	const pricing = $derived(gamePricing(item.compare));
	const price = $derived(pricing ? pricing.primary.price : ownPrice);
	const available = $derived(pricing ? pricing.primary.available : ownAvailable);
	const compareAt = $derived(
		pricing ? pricing.primary.compare_at_price : item.latest_price?.compare_at_price
	);
	const imgSrc = $derived(item.bgg?.thumbnail || item.product.image_url || '');
	// The game is the destination; the shop is a facet of it.
	const href = $derived(`/games/${gameId}?store=${encodeURIComponent(item.product.store_id)}`);
	const storeUrl = $derived(pricing?.primary.url || item.override?.url || item.product.url || '');

	// Hover trend follows whichever offer the card is quoting.
	const trendHistory = $derived(pricing ? (pricing.primary.price_history ?? []) : (history ?? []));

	// The shop the quoted price comes from — its colour is what marks it as best.
	const quotedStore = $derived(pricing ? pricing.primary.store_id : item.product.store_id);
	const storeColor = $derived(storeColors.of(quotedStore));
	// Every shop selling it, cheapest first, so the dots read as a ranking. One
	// shop can list the same game twice, so a shop gets one dot at its best price.
	const offerStores = $derived([
		...new Set(
			[...(item.compare?.offers ?? [])]
				.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity))
				.map((o) => o.store_id)
		)
	]);

	// MRP is reference, not news — it stays, but out of the price line.
	const mrpPct = $derived.by(() => {
		if (pricing) return null;
		const pct = item.discount_pct;
		return pct ? Math.round(pct) : null;
	});

	// price-range glance from history
	const range = $derived.by(() => {
		const ps = (trendHistory ?? []).map((h) => h.price).filter((n) => typeof n === 'number');
		if (ps.length < 2) return null;
		const min = Math.min(...ps);
		const max = Math.max(...ps);
		const trend = ps[0] - ps[ps.length - 1]; // history is newest-first: now - oldest
		return { min, max, trend, atLow: price != null && price <= min + 0.01 };
	});

	const fmt = (/** @type {number} */ n) =>
		`₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

	// The line under the price answers "is this a good price?" — against the
	// other shops when there are any, against its own history when there aren't.
	const standing = $derived.by(() => {
		const offers = (item.compare?.offers ?? []).filter((o) => o.price != null);
		if (pricing && offers.length > 1) {
			const worst = offers.reduce((a, b) => (b.price > a.price ? b : a));
			const saved = worst.price - price;
			return saved > 0
				? { text: `${fmt(saved)} less than ${worst.store_id}`, store: worst.store_id, good: true }
				: { text: 'same price at every shop', store: null, good: false };
		}
		if (!range || price == null) return null;
		if (range.atLow) return { text: 'cheapest it has been', store: null, good: true };
		return { text: `${fmt(price - range.min)} above its low`, store: null, good: false };
	});

	function open() {
		goto(href);
	}
	/** @param {Event} e @param {(()=>void)|null} fn */
	function act(e, fn) {
		e.stopPropagation();
		fn?.();
	}
	/** Svelte action: prevents anchor navigation when click originates from a nested button/link. */
	function cardLink(node) {
		/** @param {MouseEvent} e */
		function handler(e) {
			const t = /** @type {Element} */ (e.target);
			if (t.closest('button, [data-slot="button"]')) e.preventDefault();
		}
		node.addEventListener('click', handler);
		return { destroy: () => node.removeEventListener('click', handler) };
	}
</script>

{#if !(isHidden && variant !== 'hidden')}
	<!-- data-product-card / data-action: the j-k card cursor finds cards and
	     their buttons through the DOM, so every grid gets it for free. -->
	<a
		{href}
		data-product-card
		class="block rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
		use:cardLink
	>
		<Card.Root
			class="group relative flex cursor-pointer flex-col overflow-hidden p-0 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg hover:shadow-black/5"
		>
			<!-- Image -->
			<div class="relative aspect-[4/3] w-full" style="view-transition-name: game-{gameId}">
				<ProductImage src={imgSrc} productId={item.product.id} alt={title} class="h-full w-full" />

				<!-- permanent bottom fade: masks hard image edge, reveals more on hover -->
				<div
					class="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background/60 to-transparent transition-all duration-200 group-hover:h-0"
				></div>

				<!-- top-left flags -->
				<div class="absolute top-2 left-2 flex flex-col gap-1">
					{#if pricing}
						<Badge
							variant="outline"
							class="gap-1 bg-background/80 text-[0.7rem] backdrop-blur"
							title="Compared across {pricing.listingCount} listings"
						>
							<Store class="size-3" />
							{pricing.storeCount} stores
							<!-- Cheapest first; the ringed dot is the shop being quoted. -->
							<span class="ml-0.5 flex items-center gap-0.5">
								{#each offerStores as storeId (storeId)}
									<span
										class="size-1.5 rounded-full"
										style="background:{storeColors.of(storeId)}; {storeId === quotedStore
											? `outline:1.5px solid ${storeColors.of(storeId)}; outline-offset:1px`
											: 'opacity:0.45'}"
										title={storeId}
									></span>
								{/each}
							</span>
						</Badge>
					{/if}
					{#if range?.atLow}
						<Badge
							class="gap-1 border-green-500/30 bg-green-500/90 text-[0.7rem] text-white shadow-sm"
						>
							<TrendingDown class="size-3" /> Lowest yet
						</Badge>
					{/if}
					{#if item.override}
						<Badge
							variant="outline"
							class="bg-background/80 text-[0.7rem] text-amber-600 backdrop-blur"
						>
							overridden
						</Badge>
					{/if}
				</div>

				<!-- watch + hide toggles -->
				{#if variant === 'browse'}
					<div class="absolute top-2 right-2 flex items-center gap-1">
						<button
							data-action="hide"
							onclick={(e) => act(e, () => hidden.hide(item))}
							class="grid size-8 place-items-center rounded-full bg-background/80 text-muted-foreground shadow-sm backdrop-blur transition-all hover:scale-110 hover:bg-background hover:text-foreground active:scale-95"
							title="Hide this game permanently"
							aria-label="Hide this game"
						>
							<EyeOff class="size-4" />
						</button>
						<button
							data-action="watch"
							onclick={(e) => act(e, () => watchlist.toggle(item))}
							class="grid size-8 place-items-center rounded-full bg-background/80 shadow-sm backdrop-blur transition-all hover:scale-110 hover:bg-background active:scale-95 {watched
								? 'text-rose-500'
								: 'text-muted-foreground hover:text-rose-500'}"
							title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
							aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
							aria-pressed={watched}
						>
							<Heart class="size-4" fill={watched ? 'currentColor' : 'none'} />
						</button>
					</div>
				{/if}

				<!-- hover quick-glance: sparkline + range -->
				{#if range}
					<div
						class="pointer-events-none absolute inset-x-0 bottom-0 translate-y-1 bg-gradient-to-t from-background via-background/90 to-transparent px-3 pt-6 pb-2 opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100"
					>
						<Sparkline history={trendHistory} width={200} height={34} class="w-full" />
						<div
							class="mt-0.5 flex items-center justify-between text-[0.7rem] text-muted-foreground"
						>
							<span>{range.trend < 0 ? `High ${fmt(range.max)}` : `Low ${fmt(range.min)}`}</span>
							<span
								class="inline-flex items-center gap-0.5 {range.trend < 0
									? 'text-green-600 dark:text-green-400'
									: range.trend > 0
										? 'text-rose-500'
										: ''}"
							>
								{#if range.trend < 0}<TrendingDown
										class="size-3"
									/>{:else if range.trend > 0}<TrendingUp class="size-3" />{/if}
								{range.trend !== 0 ? fmt(Math.abs(range.trend)) : 'flat'}
							</span>
							<span>{range.trend < 0 ? `Low ${fmt(range.min)}` : `High ${fmt(range.max)}`}</span>
						</div>
					</div>
				{/if}
			</div>

			<!-- Body -->
			<div class="flex flex-1 flex-col gap-2 p-3">
				<h3 class="line-clamp-2 text-sm leading-tight font-semibold" {title}>{title}</h3>

				<div class="flex flex-wrap items-center gap-2">
					<PriceTag {price} />
					<span
						class="inline-flex items-center gap-1 text-[0.7rem] text-muted-foreground"
						title={pricing ? `Cheapest in stock: ${quotedStore}` : quotedStore}
					>
						<span class="size-1.5 rounded-full" style="background:{storeColor}" aria-hidden="true"
						></span>
						at {quotedStore}
					</span>
				</div>

				{#if standing}
					<p
						class="flex items-center gap-1 text-[0.7rem] {standing.good
							? 'text-green-600 dark:text-green-400'
							: 'text-muted-foreground'}"
					>
						{#if standing.store}
							<span
								class="size-1.5 shrink-0 rounded-full"
								style="background:{storeColors.of(standing.store)}"
								aria-hidden="true"
							></span>
						{/if}
						{standing.text}
					</p>
				{/if}

				{#if pricing?.blocked}
					<p
						class="flex items-center gap-1 text-[0.7rem] text-muted-foreground"
						title="Cheaper elsewhere but out of stock"
					>
						<XCircle class="size-3 text-rose-500" />
						<span class="line-through">{inr(pricing.blocked.price)}</span>
						at
						<span
							class="size-1.5 rounded-full"
							style="background:{storeColors.of(pricing.blocked.store_id)}"
							aria-hidden="true"
						></span>
						{pricing.blocked.store_id} — out of stock
					</p>
				{/if}

				<div class="flex items-center gap-2">
					<StockBadge {available} size="sm" />
					{#if mrpPct}
						<span class="text-[0.7rem] text-muted-foreground" title={`MRP ${fmt(compareAt)}`}>
							−{mrpPct}% off MRP
						</span>
					{/if}
					{#if variant === 'watchlist'}
						<button
							onclick={(e) => act(e, ontarget)}
							class="inline-flex items-center gap-1 rounded-full border border-dashed px-2 py-0.5 text-[0.7rem] text-muted-foreground transition hover:border-primary hover:text-foreground"
							title="Set target price"
						>
							<Target class="size-3" />
							{target != null ? `₹${target.toFixed(0)}` : 'any drop'}
						</button>
					{/if}
				</div>

				<RatingStats bgg={item.bgg} />

				<!-- actions -->
				<div class="mt-auto flex items-center gap-1.5 pt-1">
					{#if variant === 'hidden'}
						<Button
							size="sm"
							variant="outline"
							class="flex-1"
							onclick={(e) => act(e, () => hidden.unhide(item))}
						>
							<RotateCcw class="size-3.5" /> Unhide
						</Button>
					{:else if variant === 'browse'}
						{#if onedit}
							<Button
								size="icon-sm"
								variant="ghost"
								onclick={(e) => act(e, () => onedit(item))}
								title="Edit / override"
							>
								<Pencil class="size-3.5" />
							</Button>
						{/if}
						{#if storeUrl}
							<Button
								size="sm"
								variant="outline"
								href={storeUrl}
								target="_blank"
								class="flex-1"
								style="border-color:{tint(storeColor, 0.55)}; background:{tint(storeColor, 0.08)}"
								onclick={(e) => e.stopPropagation()}
							>
								<ExternalLink class="size-3.5" />
								{pricing ? 'Best store' : 'Store'}
							</Button>
						{/if}
					{:else}
						{#if item.product.url}
							<Button
								size="sm"
								variant="outline"
								href={item.product.url}
								target="_blank"
								class="flex-1"
								onclick={(e) => e.stopPropagation()}
							>
								<ExternalLink class="size-3.5" /> Store
							</Button>
						{/if}
						<Button size="sm" variant="outline" class="flex-1" onclick={(e) => act(e, open)}>
							Details
						</Button>
						{#if onremove}
							<Button
								size="icon-sm"
								variant="destructive"
								onclick={(e) => act(e, onremove)}
								title="Remove from watchlist"
							>
								<Trash2 class="size-3.5" />
							</Button>
						{/if}
					{/if}
				</div>
			</div>
		</Card.Root>
	</a>
{/if}
