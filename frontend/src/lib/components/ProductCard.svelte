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
	import { cart } from '$lib/cart.svelte.js';
	import { gamePricing } from '$lib/gamePricing.js';
	import { inr, roundPrice } from '$lib/priceFormat.svelte.js';
	import { lastPriceChange } from '$lib/priceChange.js';
	import { linkBgg, updateWatchlist } from '$lib/api.js';
	import { toast } from '$lib/toast.svelte.js';
	import { parseBggId, bggGameUrl, bggSearchUrl } from '$lib/bgg.js';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import {
		Heart,
		Pencil,
		ExternalLink,
		Target,
		TrendingDown,
		TrendingUp,
		Eye,
		EyeOff,
		Store,
		XCircle,
		Dices,
		ShoppingCart
	} from '@lucide/svelte';

	let {
		item,
		onedit = /** @type {((item:any)=>void)|null} */ (null),
		onlinked = /** @type {((bggId:number)=>void)|null} */ (null)
	} = $props();

	const gameId = $derived(item.game?.id ?? item.product.game_id);
	const watched = $derived(watchlist.has(gameId));
	const isHidden = $derived(hidden.has(gameId));
	const queued = $derived(cart.has(gameId));

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
	const imgSrc = $derived(item.bgg?.thumbnail || item.product.image_url || '');
	// The game is the destination; the shop is a facet of it.
	const href = $derived(`/games/${gameId}?store=${encodeURIComponent(item.product.store_id)}`);
	const storeUrl = $derived(pricing?.primary.url || item.override?.url || item.product.url || '');

	// Hover trend follows whichever offer the card is quoting. A one-shop game
	// has no `compare`, so it reads the listing's own readings off the card.
	const trendHistory = $derived(
		pricing ? (pricing.primary.price_history ?? []) : (item.price_history ?? [])
	);

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

	// How long the quoted price has stood — a shop's own MRP says less.
	const held = $derived(lastPriceChange(trendHistory));

	// price-range glance from history
	const range = $derived.by(() => {
		const ps = (trendHistory ?? []).map((h) => h.price).filter((n) => typeof n === 'number');
		if (ps.length < 2) return null;
		const min = Math.min(...ps);
		const max = Math.max(...ps);
		// Rounded on each side, so the delta agrees with the High/Low it sits between.
		const trend = roundPrice(ps[0]) - roundPrice(ps[ps.length - 1]); // newest-first: now - oldest
		return { min, max, trend, atLow: price != null && price <= min + 0.01 };
	});

	// The line under the price answers "is this a good price?" — against the
	// other shops when there are any, against its own history when there aren't.
	const standing = $derived.by(() => {
		const offers = (item.compare?.offers ?? []).filter((o) => o.price != null);
		if (pricing && offers.length > 1) {
			const worst = offers.reduce((a, b) => (b.price > a.price ? b : a));
			const saved = roundPrice(worst.price) - roundPrice(price);
			return saved > 0
				? { text: `${inr(saved)} less than ${worst.store_id}`, store: worst.store_id, good: true }
				: { text: 'same price at every shop', store: null, good: false };
		}
		if (!range || price == null) return null;
		if (range.atLow) return { text: 'cheapest it has been', store: null, good: true };
		// A gap that rounds away must not claim the low that `atLow` reserves.
		const above = roundPrice(price) - roundPrice(range.min);
		return above > 0
			? { text: `${inr(above)} above its low`, store: null, good: false }
			: { text: 'near its lowest', store: null, good: false };
	});

	function open() {
		goto(href);
	}
	/** @param {Event} e @param {(()=>void)|null} fn */
	function act(e, fn) {
		e.stopPropagation();
		fn?.();
	}

	// A target belongs to the watch, so any watched card can set one. Local
	// override so the chip settles without waiting for the payload to refetch.
	let targetEdit = $state(/** @type {number|null|undefined} */ (undefined));
	const target = $derived(
		targetEdit !== undefined ? targetEdit : (item.watchlist?.target_price ?? null)
	);

	async function setTarget() {
		const val = prompt('Target price (₹) — blank for any drop:', target ?? '');
		if (val === null) return;
		const next = val ? parseFloat(val) : null;
		try {
			await updateWatchlist(item.watchlist.id, next);
			targetEdit = next;
			toast.success('Target updated');
		} catch (e) {
			toast.error(e.message);
		}
	}

	// BGG linking from the card: the pill opens a search, the field takes the
	// pasted link. Linking is local state so the pill flips without a refetch.
	let linkedId = $state(/** @type {number|null} */ (null));
	let bggOpen = $state(false);
	let bggUrl = $state('');
	let linking = $state(false);

	const bggId = $derived(linkedId ?? item.game?.bgg_id ?? null);
	const bggHref = $derived(item.bgg?.bgg_url || bggGameUrl(bggId));

	function findOnBgg() {
		bggOpen = true;
		window.open(bggSearchUrl(title), '_blank', 'noopener');
	}

	async function linkPasted() {
		const id = parseBggId(bggUrl);
		if (!id || linking) return;
		linking = true;
		try {
			await linkBgg(id, item.product.id);
			linkedId = id;
			bggOpen = false;
			bggUrl = '';
			toast.success('Linked to BGG');
			onlinked?.(id);
		} catch (e) {
			toast.error(e.message);
		} finally {
			linking = false;
		}
	}

	/** @param {HTMLElement} node */
	function focused(node) {
		node.focus();
	}

	/** Svelte action: prevents anchor navigation when click originates from a nested button/link. */
	function cardLink(node) {
		/** @param {MouseEvent} e */
		function handler(e) {
			const t = /** @type {Element} */ (e.target);
			if (t.closest('button, input, [data-slot="button"]')) e.preventDefault();
		}
		node.addEventListener('click', handler);
		return { destroy: () => node.removeEventListener('click', handler) };
	}
</script>

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
				{#if isHidden}
					<Badge
						variant="outline"
						class="gap-1 bg-background/80 text-[0.7rem] text-muted-foreground backdrop-blur"
					>
						<EyeOff class="size-3" /> Hidden
					</Badge>
				{/if}
				{#if queued}
					<Badge
						variant="outline"
						class="gap-1 bg-background/80 text-[0.7rem] text-primary backdrop-blur"
					>
						<ShoppingCart class="size-3" /> In cart
					</Badge>
				{/if}
			</div>

			<!-- queue + watch + hide toggles -->
			<div class="absolute top-2 right-2 flex items-center gap-1">
				<button
					data-action="cart"
					onclick={(e) => act(e, () => cart.toggle(item))}
					class="grid size-8 place-items-center rounded-full bg-background/80 shadow-sm backdrop-blur transition-all hover:scale-110 hover:bg-background active:scale-95 {queued
						? 'text-primary'
						: 'text-muted-foreground hover:text-primary'}"
					title={queued ? 'Remove from your cart' : 'Add to your cart'}
					aria-label={queued ? 'Remove from cart' : 'Add to cart'}
					aria-pressed={queued}
				>
					<ShoppingCart class="size-4" fill={queued ? 'currentColor' : 'none'} />
				</button>
				<button
					data-action="hide"
					onclick={(e) => act(e, () => (isHidden ? hidden.unhide(item) : hidden.hide(item)))}
					class="grid size-8 place-items-center rounded-full bg-background/80 text-muted-foreground shadow-sm backdrop-blur transition-all hover:scale-110 hover:bg-background hover:text-foreground active:scale-95"
					title={isHidden ? 'Unhide this game' : 'Hide this game permanently'}
					aria-label={isHidden ? 'Unhide this game' : 'Hide this game'}
					aria-pressed={isHidden}
				>
					{#if isHidden}<Eye class="size-4" />{:else}<EyeOff class="size-4" />{/if}
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

			<!-- hover quick-glance: sparkline + range -->
			{#if range}
				<div
					class="pointer-events-none absolute inset-x-0 bottom-0 translate-y-1 bg-gradient-to-t from-background via-background/90 to-transparent px-3 pt-6 pb-2 opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100"
				>
					<Sparkline history={trendHistory} width={200} height={34} class="w-full" />
					<div class="mt-0.5 flex items-center justify-between text-[0.7rem] text-muted-foreground">
						<span>{range.trend < 0 ? `High ${inr(range.max)}` : `Low ${inr(range.min)}`}</span>
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
							{range.trend !== 0 ? inr(Math.abs(range.trend)) : 'flat'}
						</span>
						<span>{range.trend < 0 ? `Low ${inr(range.min)}` : `High ${inr(range.max)}`}</span>
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
				{#if held}
					<span class="text-[0.7rem] text-muted-foreground">
						{held.changed ? `changed ${held.label} ago` : `same for ${held.label}`}
					</span>
				{/if}
				{#if item.watchlist}
					<button
						onclick={(e) => act(e, setTarget)}
						class="inline-flex items-center gap-1 rounded-full border border-dashed px-2 py-0.5 text-[0.7rem] text-muted-foreground transition hover:border-primary hover:text-foreground"
						title="Set target price"
					>
						<Target class="size-3" />
						{target != null ? inr(target) : 'any drop'}
					</button>
				{/if}
			</div>

			<RatingStats bgg={item.bgg} />

			{#if bggOpen && !bggHref}
				<input
					use:focused
					bind:value={bggUrl}
					oninput={linkPasted}
					onclick={(e) => e.stopPropagation()}
					disabled={linking}
					placeholder="Paste BGG link…"
					aria-label="Paste BGG link"
					class="h-7 w-full rounded-md border bg-background px-2 text-xs focus:ring-2 focus:ring-ring focus:outline-none"
				/>
			{/if}

			<!-- actions -->
			<div class="mt-auto flex items-center gap-1.5 pt-1">
				{#if bggHref}
					<Button
						data-action="bgg"
						size="icon-sm"
						variant="ghost"
						href={bggHref}
						target="_blank"
						rel="noopener"
						title="Open on BoardGameGeek"
						aria-label="Open on BoardGameGeek"
						onclick={(e) => e.stopPropagation()}
					>
						<Dices class="size-3.5" />
					</Button>
				{:else}
					<Button
						data-action="bgg"
						size="icon-sm"
						variant="ghost"
						class="text-muted-foreground/60"
						onclick={(e) => act(e, findOnBgg)}
						title="Find on BoardGameGeek and paste the link"
						aria-label="Find on BoardGameGeek"
					>
						<Dices class="size-3.5" />
					</Button>
				{/if}
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
			</div>
		</div>
	</Card.Root>
</a>
