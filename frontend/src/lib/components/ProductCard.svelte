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
	import {
		Heart,
		Pencil,
		ExternalLink,
		Trash2,
		Target,
		TrendingDown,
		TrendingUp,
		EyeOff,
		RotateCcw
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

	const watched = $derived(watchlist.has(item.product.id));
	const isHidden = $derived(hidden.has(item.product.id));

	const title = $derived(item.override?.title || item.product.title);
	const price = $derived(
		item.override?.override_price != null
			? item.override.override_price
			: (item.latest_price?.price ?? null)
	);
	const available = $derived(
		item.override?.override_available != null
			? item.override.override_available
			: (item.latest_price?.available ?? false)
	);
	const imgSrc = $derived(item.bgg?.thumbnail || item.product.image_url || '');
	const href = $derived(`/prices/${item.product.id}`);

	// price-range glance from history
	const range = $derived.by(() => {
		const ps = (history ?? []).map((h) => h.price).filter((n) => typeof n === 'number');
		if (ps.length < 2) return null;
		const min = Math.min(...ps);
		const max = Math.max(...ps);
		const trend = ps[0] - ps[ps.length - 1]; // history is newest-first: now - oldest
		return { min, max, trend, atLow: price != null && price <= min + 0.01 };
	});

	const fmt = (/** @type {number} */ n) =>
		`₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

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
			<div
				class="relative aspect-[4/3] w-full"
				style="view-transition-name: product-{item.product.id}"
			>
				<ProductImage src={imgSrc} productId={item.product.id} alt={title} class="h-full w-full" />

				<!-- permanent bottom fade: masks hard image edge, reveals more on hover -->
				<div
					class="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background/60 to-transparent transition-all duration-200 group-hover:h-0"
				></div>

				<!-- top-left flags -->
				<div class="absolute top-2 left-2 flex flex-col gap-1">
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
						<Sparkline {history} width={200} height={34} class="w-full" />
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
					<PriceTag
						{price}
						compareAt={item.latest_price?.compare_at_price}
						discountPct={item.discount_pct}
					/>
				</div>

				<div class="flex items-center gap-2">
					<StockBadge {available} size="sm" />
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
							onclick={(e) => act(e, () => hidden.unhide(item.product.id))}
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
						{#if item.product.url || item.override?.url}
							<Button
								size="sm"
								variant="outline"
								href={item.override?.url || item.product.url}
								target="_blank"
								class="flex-1"
								onclick={(e) => e.stopPropagation()}
							>
								<ExternalLink class="size-3.5" /> Store
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
