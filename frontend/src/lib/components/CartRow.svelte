<script>
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import ProductImage from './ProductImage.svelte';
	import StockBadge from './StockBadge.svelte';
	import Sparkline from './Sparkline.svelte';
	import MarkdownNote from './MarkdownNote.svelte';
	import { inr, inrDelta } from '$lib/priceFormat.svelte.js';
	import { storeColors, tint } from '$lib/storeColors.svelte.js';
	import { PRIORITIES, rowLine } from '$lib/cartView.js';
	import {
		GripVertical,
		ArrowUp,
		ArrowDown,
		ExternalLink,
		Trash2,
		Check,
		Pin,
		PinOff,
		Star,
		TrendingDown,
		TrendingUp,
		AlertTriangle,
		Minus,
		Plus,
		Target
	} from '@lucide/svelte';

	/**
	 * @type {{
	 *   row: any,
	 *   index: number,
	 *   count: number,
	 *   draggable?: boolean,
	 *   dragging?: boolean,
	 *   onpatch: (body: any) => void,
	 *   onmove: (to: number) => void,
	 *   onremove: () => void,
	 *   onbuy: () => void
	 * }}
	 */
	let {
		row,
		index,
		count,
		draggable = true,
		dragging = false,
		onpatch,
		onmove,
		onremove,
		onbuy
	} = $props();

	const item = $derived(row.cart);
	const offer = $derived(row.offer);
	const card = $derived(row.card);
	const title = $derived(card?.game?.title ?? offer?.listing_title ?? 'Unknown game');
	const gameHref = $derived(`/games/${item.game_id}`);
	const offers = $derived(row.compare?.offers ?? []);
	const storeColor = $derived(storeColors.of(offer?.store_id));
	const line = $derived(rowLine(row));
	const history = $derived(card?.price_history ?? []);

	/** @param {Event} e */
	function pickStore(e) {
		const value = /** @type {HTMLSelectElement} */ (e.currentTarget).value;
		onpatch(value === 'auto' ? { unpin: true } : { product_id: Number(value) });
	}

	function setMax() {
		const val = prompt('Buy at or below (₹) — blank to clear:', item.max_price ?? '');
		if (val === null) return;
		onpatch(val ? { max_price: parseFloat(val) } : { clear_max_price: true });
	}
</script>

<div
	{draggable}
	class="rounded-xl border bg-card p-3 transition-shadow hover:shadow-sm"
	class:opacity-50={dragging}
	class:ring-2={dragging}
	class:ring-primary={dragging}
>
	<div class="flex gap-3">
		<!-- order controls -->
		<div class="flex shrink-0 flex-col items-center gap-1 pt-0.5">
			{#if draggable}
				<GripVertical class="size-4 cursor-grab text-muted-foreground active:cursor-grabbing" />
			{/if}
			<span class="text-xs font-semibold text-muted-foreground tabular-nums">{index + 1}</span>
			<Button
				variant="ghost"
				size="icon-sm"
				disabled={index === 0}
				onclick={() => onmove(index - 1)}
				aria-label={`Move ${title} up`}
			>
				<ArrowUp class="size-3.5" />
			</Button>
			<Button
				variant="ghost"
				size="icon-sm"
				disabled={index === count - 1}
				onclick={() => onmove(index + 1)}
				aria-label={`Move ${title} down`}
			>
				<ArrowDown class="size-3.5" />
			</Button>
		</div>

		<a href={gameHref} class="size-20 shrink-0 overflow-hidden rounded-lg sm:size-24">
			<ProductImage
				src={card?.bgg?.thumbnail || card?.product?.image_url || ''}
				productId={card?.product?.id}
				alt={title}
				class="h-full w-full"
			/>
		</a>

		<div class="flex min-w-0 flex-1 flex-col gap-2">
			<div class="flex flex-wrap items-start justify-between gap-2">
				<div class="min-w-0">
					<a href={gameHref} class="text-sm font-semibold hover:underline">{title}</a>
					<div class="mt-0.5 flex flex-wrap items-center gap-2 text-[0.7rem] text-muted-foreground">
						{#if card?.bgg?.bgg_rating}
							<span class="inline-flex items-center gap-0.5">
								<Star class="size-3 text-amber-500" />
								{card.bgg.bgg_rating.toFixed(1)}
							</span>
						{/if}
						{#if card?.bgg?.avg_weight}
							<span>weight {card.bgg.avg_weight.toFixed(1)}</span>
						{/if}
						{#if offer}
							<StockBadge available={offer.available} size="sm" />
						{/if}
					</div>
				</div>

				<div class="text-right">
					<div class="text-base font-semibold">{line == null ? '—' : inr(line)}</div>
					{#if item.quantity > 1 && offer?.price != null}
						<div class="text-[0.7rem] text-muted-foreground">
							{item.quantity} × {inr(offer.price)}
						</div>
					{/if}
					{#if row.price_move}
						<div
							class="inline-flex items-center gap-0.5 text-[0.7rem] {row.price_move < 0
								? 'text-green-600 dark:text-green-400'
								: 'text-rose-500'}"
							title="Since you queued it"
						>
							{#if row.price_move < 0}<TrendingDown class="size-3" />{:else}<TrendingUp
									class="size-3"
								/>{/if}
							{inrDelta(row.price_move)}
						</div>
					{/if}
				</div>
			</div>

			{#if row.over_max}
				<p class="flex items-center gap-1 text-[0.7rem] text-amber-600">
					<AlertTriangle class="size-3" />
					Over your {inr(item.max_price)} limit
				</p>
			{/if}

			<!-- shop, quantity, ceiling, priority -->
			<div class="flex flex-wrap items-center gap-1.5">
				<label class="sr-only" for={`store-${item.id}`}>Buy from</label>
				<select
					id={`store-${item.id}`}
					value={item.product_id ?? 'auto'}
					onchange={pickStore}
					class="h-7 rounded-md border bg-background px-1.5 text-xs focus:ring-2 focus:ring-ring focus:outline-none"
					style="border-color:{tint(storeColor, 0.55)}; background:{tint(storeColor, 0.08)}"
				>
					<option value="auto">Cheapest in stock</option>
					{#each offers as o (o.product_id)}
						<option value={o.product_id}>
							{o.store_id} — {o.price == null ? 'no price' : inr(o.price)}{o.available
								? ''
								: ' (out)'}
						</option>
					{/each}
				</select>
				<span
					class="inline-flex items-center gap-1 text-[0.7rem] text-muted-foreground"
					title={row.pinned ? 'Pinned to this shop' : 'Follows the cheapest buyable offer'}
				>
					{#if row.pinned}<Pin class="size-3" />{:else}<PinOff class="size-3" />{/if}
					{offer?.store_id ?? 'no offer'}
				</span>

				<div class="ml-auto flex items-center gap-1 rounded-md border">
					<button
						class="grid size-6 place-items-center text-muted-foreground hover:text-foreground disabled:opacity-40"
						disabled={item.quantity <= 1}
						onclick={() => onpatch({ quantity: item.quantity - 1 })}
						aria-label="Decrease quantity"
					>
						<Minus class="size-3" />
					</button>
					<span class="min-w-4 text-center text-xs tabular-nums">{item.quantity}</span>
					<button
						class="grid size-6 place-items-center text-muted-foreground hover:text-foreground"
						onclick={() => onpatch({ quantity: item.quantity + 1 })}
						aria-label="Increase quantity"
					>
						<Plus class="size-3" />
					</button>
				</div>

				<button
					onclick={setMax}
					class="inline-flex items-center gap-1 rounded-full border border-dashed px-2 py-0.5 text-[0.7rem] text-muted-foreground transition hover:border-primary hover:text-foreground"
					title="Buy-at ceiling for this row"
				>
					<Target class="size-3" />
					{item.max_price != null ? inr(item.max_price) : 'no limit'}
				</button>

				<label class="sr-only" for={`priority-${item.id}`}>Priority</label>
				<select
					id={`priority-${item.id}`}
					value={item.priority}
					onchange={(e) => onpatch({ priority: e.currentTarget.value })}
					class="h-7 rounded-md border bg-background px-1.5 text-xs focus:ring-2 focus:ring-ring focus:outline-none"
				>
					{#each PRIORITIES as p (p.id)}
						<option value={p.id}>{p.label}</option>
					{/each}
				</select>
			</div>

			{#if history.length > 1}
				<Sparkline {history} width={220} height={26} class="w-full max-w-[220px]" />
			{/if}

			<MarkdownNote
				value={item.note}
				placeholder="Why this one? Editions, expansions, who it's for…"
				onsave={(next) => onpatch({ note: next })}
			/>

			<div class="flex flex-wrap items-center gap-1.5">
				{#if offer?.url}
					<Button
						size="sm"
						variant="outline"
						href={offer.url}
						target="_blank"
						rel="noopener"
						style="border-color:{tint(storeColor, 0.55)}; background:{tint(storeColor, 0.08)}"
					>
						<ExternalLink class="size-3.5" /> Open {offer.store_id}
					</Button>
				{/if}
				<Button size="sm" variant="ghost" onclick={onbuy}>
					<Check class="size-3.5" /> Bought it
				</Button>
				<Button
					size="sm"
					variant="ghost"
					class="text-muted-foreground hover:text-destructive"
					onclick={onremove}
				>
					<Trash2 class="size-3.5" /> Remove
				</Button>
				{#if card?.watchlist}
					<Badge variant="outline" class="text-[0.7rem]">watched</Badge>
				{/if}
			</div>
		</div>
	</div>
</div>
