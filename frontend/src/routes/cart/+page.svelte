<script>
	import { onMount } from 'svelte';
	import { flip } from 'svelte/animate';
	import {
		getCart,
		getPurchased,
		patchCartItem,
		removeFromCart,
		reorderCart,
		markCartPurchased,
		unmarkCartPurchased,
		setCartBudget
	} from '$lib/api.js';
	import { cart as cartStore } from '$lib/cart.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import { Button } from '$lib/components/ui/button';
	import CartRow from '$lib/components/CartRow.svelte';
	import CartSummary from '$lib/components/CartSummary.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { inr } from '$lib/priceFormat.svelte.js';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { SORTS, PRIORITIES, filterRows, sortRows, storeOptions } from '$lib/cartView.js';
	import { ShoppingCart, Scissors, RotateCcw, PackageCheck } from '@lucide/svelte';

	let loading = $state(true);
	let rows = $state(/** @type {any[]} */ ([]));
	let summary = $state(/** @type {any} */ ({ count: 0, total: 0, by_store: [] }));
	let switches = $state(/** @type {any[]} */ ([]));
	let bought = $state(/** @type {any[]} */ ([]));
	let showBought = $state(false);

	let sort = $state('order');
	let priority = $state(/** @type {string|null} */ (null));
	let storeId = $state(/** @type {string|null} */ (null));
	let inStockOnly = $state(false);
	let withinBudget = $state(false);
	let dragIndex = $state(/** @type {number|null} */ (null));

	// Reordering is only meaningful against the queue's own order — any other
	// sort is a lens over it, so dragging is off while one is applied.
	const manual = $derived(
		sort === 'order' && !priority && !storeId && !inStockOnly && !withinBudget
	);

	const visible = $derived(
		sortRows(
			filterRows(rows, {
				priority,
				storeId,
				inStockOnly,
				withinBudget,
				cutIndex: summary.cut_index
			}),
			sort
		)
	);
	const stores = $derived(storeOptions(rows));

	/** @param {any} payload */
	function apply(payload) {
		rows = payload.items;
		summary = payload.summary;
		switches = payload.switches ?? [];
		cartStore.sync(rows);
	}

	async function load() {
		try {
			apply(await getCart());
		} catch (e) {
			toast.error(e.message);
		} finally {
			loading = false;
		}
	}

	async function loadBought() {
		try {
			bought = (await getPurchased()).items;
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {number} id @param {any} body */
	async function patch(id, body) {
		try {
			await patchCartItem(id, body);
			await load();
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {any} row */
	async function remove(row) {
		try {
			await removeFromCart(row.cart.id);
			toast.success('Removed from cart');
			await load();
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {any} row */
	async function buy(row) {
		try {
			await markCartPurchased(row.cart.id);
			toast.success(`Marked ${row.card?.game?.title ?? 'it'} as bought`);
			await load();
			if (showBought) await loadBought();
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {any} row */
	async function unbuy(row) {
		try {
			await unmarkCartPurchased(row.cart.id);
			await Promise.all([load(), loadBought()]);
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {number} from @param {number} to */
	function reorderLocal(from, to) {
		if (to < 0 || to >= rows.length || from === to) return;
		const next = [...rows];
		const [moved] = next.splice(from, 1);
		next.splice(to, 0, moved);
		rows = next;
	}

	async function saveOrder() {
		try {
			apply(await reorderCart(rows.map((r) => r.cart.id)));
		} catch (e) {
			toast.error(e.message);
		}
	}

	/** @param {number} from @param {number} to */
	async function move(from, to) {
		if (to < 0 || to >= rows.length) return;
		reorderLocal(from, to);
		await saveOrder();
	}

	/** @param {number} index */
	function dragOver(index) {
		if (dragIndex === null || dragIndex === index) return;
		reorderLocal(dragIndex, index);
		dragIndex = index;
	}

	/** @param {number|null} amount */
	async function saveBudget(amount) {
		try {
			await setCartBudget(amount);
			await load();
		} catch (e) {
			toast.error(e.message);
		}
	}

	async function switchAll() {
		try {
			for (const s of switches) await patchCartItem(s.cart_id, { product_id: s.to_product_id });
			toast.success('Switched to the cheapest shops');
			await load();
		} catch (e) {
			toast.error(e.message);
		}
	}

	function toggleBought() {
		showBought = !showBought;
		if (showBought && bought.length === 0) loadBought();
	}

	onMount(load);
</script>

<svelte:head><title>Cart · GameDrop</title></svelte:head>

<div class="space-y-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<ShoppingCart class="size-6 text-primary" />
			Cart
		</h1>
		<Button variant="ghost" size="sm" onclick={toggleBought}>
			<PackageCheck class="size-4" />
			{showBought ? 'Hide' : 'Show'} bought
		</Button>
	</div>

	{#if loading}
		<Skeleton class="h-32 w-full rounded-xl" />
		<Skeleton class="h-28 w-full rounded-xl" />
		<Skeleton class="h-28 w-full rounded-xl" />
	{:else if rows.length === 0}
		<div class="rounded-xl border border-dashed px-6 py-16 text-center">
			<ShoppingCart class="mx-auto size-8 text-muted-foreground" />
			<p class="mt-3 font-medium">Your cart is empty</p>
			<p class="mt-1 text-sm text-muted-foreground">
				Add games from any grid with the cart button, then come back to order them.
			</p>
			<Button href="/browse" class="mt-4">Browse games</Button>
		</div>
	{:else}
		<CartSummary {summary} {switches} onbudget={saveBudget} onswitchall={switchAll} />

		<!-- narrowing controls -->
		<div class="flex flex-wrap items-center gap-2 text-xs">
			<label class="sr-only" for="cart-sort">Sort</label>
			<select
				id="cart-sort"
				bind:value={sort}
				class="h-8 rounded-md border bg-background px-2 focus:ring-2 focus:ring-ring focus:outline-none"
			>
				{#each SORTS as s (s.id)}
					<option value={s.id}>{s.label}</option>
				{/each}
			</select>

			<button
				onclick={() => (priority = null)}
				class="rounded-full border px-2.5 py-1 transition {priority === null
					? 'border-primary bg-primary/10 text-primary'
					: 'text-muted-foreground hover:bg-muted'}">All</button
			>
			{#each PRIORITIES as p (p.id)}
				<button
					onclick={() => (priority = priority === p.id ? null : p.id)}
					class="rounded-full border px-2.5 py-1 transition {priority === p.id
						? 'border-primary bg-primary/10 text-primary'
						: 'text-muted-foreground hover:bg-muted'}">{p.label}</button
				>
			{/each}

			{#each stores as s (s.id)}
				<button
					onclick={() => (storeId = storeId === s.id ? null : s.id)}
					class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 transition {storeId ===
					s.id
						? 'border-primary bg-primary/10 text-primary'
						: 'text-muted-foreground hover:bg-muted'}"
				>
					<span class="size-1.5 rounded-full" style="background:{storeColors.of(s.id)}"></span>
					{s.id}
					<span class="opacity-60">{s.count}</span>
				</button>
			{/each}

			<button
				onclick={() => (inStockOnly = !inStockOnly)}
				class="rounded-full border px-2.5 py-1 transition {inStockOnly
					? 'border-primary bg-primary/10 text-primary'
					: 'text-muted-foreground hover:bg-muted'}">In stock</button
			>
			{#if summary.cut_index != null}
				<button
					onclick={() => (withinBudget = !withinBudget)}
					class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 transition {withinBudget
						? 'border-primary bg-primary/10 text-primary'
						: 'text-muted-foreground hover:bg-muted'}"
				>
					<Scissors class="size-3" /> Fits the budget
				</button>
			{/if}

			<span class="ml-auto text-muted-foreground">
				{visible.length} of {rows.length} shown
				{#if !manual}· drag off while filtered or sorted{/if}
			</span>
		</div>

		<ul class="space-y-2">
			{#each visible as row, i (row.cart.id)}
				<li
					animate:flip={{ duration: 180 }}
					role="presentation"
					ondragstart={() => manual && (dragIndex = i)}
					ondragover={(e) => {
						if (!manual) return;
						e.preventDefault();
						dragOver(i);
					}}
					ondragend={() => {
						if (dragIndex === null) return;
						dragIndex = null;
						saveOrder();
					}}
					ondrop={(e) => e.preventDefault()}
				>
					<!-- The cutline sits in the queue's own order: everything above it is
					     what the budget actually reaches at today's prices. -->
					{#if manual && summary.cut_index === i}
						<p class="flex items-center gap-2 pb-2 text-[0.7rem] text-muted-foreground">
							<span class="h-px flex-1 bg-border"></span>
							<Scissors class="size-3" />
							{inr(summary.budget)} budget ends here
							<span class="h-px flex-1 bg-border"></span>
						</p>
					{/if}
					<CartRow
						{row}
						index={i}
						count={visible.length}
						draggable={manual}
						dragging={dragIndex === i}
						onpatch={(body) => patch(row.cart.id, body)}
						onmove={(to) => move(i, to)}
						onremove={() => remove(row)}
						onbuy={() => buy(row)}
					/>
				</li>
			{/each}
		</ul>
	{/if}

	{#if showBought}
		<section class="space-y-2">
			<h2 class="text-sm font-semibold tracking-tight">Bought</h2>
			{#if bought.length === 0}
				<p
					class="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground"
				>
					Nothing marked as bought yet.
				</p>
			{:else}
				<ul class="divide-y rounded-xl border">
					{#each bought as row (row.cart.id)}
						<li class="flex items-center gap-3 px-3 py-2 text-sm">
							<a
								href={`/games/${row.cart.game_id}`}
								class="min-w-0 flex-1 truncate hover:underline"
							>
								{row.card?.game?.title ?? 'Unknown game'}
							</a>
							<span class="text-muted-foreground tabular-nums">
								{row.cart.purchased_price != null ? inr(row.cart.purchased_price) : '—'}
							</span>
							<Button variant="ghost" size="sm" onclick={() => unbuy(row)}>
								<RotateCcw class="size-3.5" /> Back to cart
							</Button>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/if}
</div>
