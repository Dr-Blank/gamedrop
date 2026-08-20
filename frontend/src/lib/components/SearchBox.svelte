<script>
	import { goto } from '$app/navigation';
	import { searchCatalog } from '$lib/api.js';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { gamePricing, inr } from '$lib/gamePricing.js';
	import ProductImage from './ProductImage.svelte';
	import { Search, Heart } from '@lucide/svelte';

	let {
		placeholder = 'Search…',
		class: className = '',
		inputClass = '',
		hint = false,
		onnavigate = /** @type {(()=>void)|null} */ (null)
	} = $props();

	const DEBOUNCE_MS = 200;
	const LIMIT = 6;

	let q = $state('');
	let results = $state(/** @type {any[]} */ ([]));
	let open = $state(false);
	let active = $state(-1);
	let focused = $state(false);
	/** @type {HTMLInputElement | null} */
	let input = $state(null);
	/** @type {HTMLElement | null} */
	let root = $state(null);

	let timer = /** @type {any} */ (null);
	// Fast typing answers out of order, so only the newest query may paint.
	let seq = 0;

	export function focus() {
		input?.select();
	}

	export function isVisible() {
		return !!input?.offsetParent;
	}

	function schedule() {
		clearTimeout(timer);
		const term = q.trim();
		if (term.length < 2) {
			results = [];
			open = false;
			return;
		}
		timer = setTimeout(() => run(term), DEBOUNCE_MS);
	}

	/** @param {string} term */
	async function run(term) {
		const mine = ++seq;
		try {
			const res = await searchCatalog(term, LIMIT);
			if (mine !== seq) return;
			results = res.items ?? [];
			active = -1;
			open = results.length > 0;
		} catch {
			if (mine === seq) {
				results = [];
				open = false;
			}
		}
	}

	function close() {
		open = false;
		active = -1;
	}

	function reset() {
		clearTimeout(timer);
		seq++;
		q = '';
		results = [];
		close();
		onnavigate?.();
	}

	/** @param {any} item */
	function href(item) {
		const gameId = item.game?.id ?? item.product.game_id;
		return `/games/${gameId}?store=${encodeURIComponent(item.product.store_id)}`;
	}

	/** @param {any} item */
	function go(item) {
		const target = href(item);
		reset();
		goto(target);
	}

	function submit() {
		if (active >= 0 && results[active]) {
			go(results[active]);
			return;
		}
		submitAll();
	}

	function submitAll() {
		const term = q.trim();
		if (!term) return;
		reset();
		goto(`/search?q=${encodeURIComponent(term)}`);
	}

	/** @param {KeyboardEvent} e */
	function onkeydown(e) {
		if (e.key === 'Escape') {
			close();
			return;
		}
		if (!open) return;
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			active = (active + 1) % results.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			active = active <= 0 ? results.length - 1 : active - 1;
		}
	}

	/** @param {any} item */
	function price(item) {
		const pricing = gamePricing(item.compare);
		return pricing ? pricing.primary.price : (item.latest_price?.price ?? null);
	}

	/** @param {any} item */
	function storeId(item) {
		const pricing = gamePricing(item.compare);
		return pricing ? pricing.primary.store_id : item.product.store_id;
	}

	// One shop is named; several are counted — the price already says which one
	// it comes from is the cheapest.
	/** @param {any} item */
	function stores(item) {
		const pricing = gamePricing(item.compare);
		if (!pricing || pricing.storeCount < 2) return { label: storeId(item), ids: [storeId(item)] };
		const ids = [
			...new Set(
				[...(item.compare?.offers ?? [])]
					.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity))
					.map((o) => o.store_id)
			)
		];
		return { label: `${pricing.storeCount} stores`, ids };
	}
</script>

<svelte:window
	onpointerdown={(e) => {
		if (root && !root.contains(/** @type {Node} */ (e.target))) close();
	}}
/>

<div bind:this={root} class="relative {className}">
	<form
		onsubmit={(e) => {
			e.preventDefault();
			submit();
		}}
	>
		<Search
			class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
		/>
		<input
			bind:this={input}
			bind:value={q}
			oninput={schedule}
			{onkeydown}
			onfocus={() => {
				focused = true;
				if (results.length) open = true;
			}}
			onblur={() => (focused = false)}
			{placeholder}
			role="combobox"
			aria-expanded={open}
			aria-controls="search-suggestions"
			aria-autocomplete="list"
			aria-activedescendant={active >= 0 ? `search-suggestion-${active}` : undefined}
			aria-keyshortcuts="/ Control+K"
			class="w-full rounded-lg border bg-background text-sm transition-colors focus:ring-2 focus:ring-ring focus:outline-none {inputClass}"
		/>
		<!-- Hint, not a control: it would only be in the way once typing starts. -->
		{#if hint && !focused && !q}
			<kbd
				class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
			>
				/
			</kbd>
		{/if}
	</form>

	{#if open}
		<div
			class="absolute top-full right-0 left-auto z-50 mt-1 w-[min(24rem,calc(100vw-2rem))] min-w-full overflow-hidden rounded-lg border bg-background shadow-lg"
		>
			<ul
				id="search-suggestions"
				role="listbox"
				aria-label="Search suggestions"
				onmouseleave={() => (active = -1)}
				class="max-h-[26rem] overflow-y-auto"
			>
				{#each results as item, i (item.product.id)}
					{@const gameId = item.game?.id ?? item.product.game_id}
					{@const watched = watchlist.has(gameId)}
					{@const shops = stores(item)}
					<li
						id="search-suggestion-{i}"
						role="option"
						aria-selected={i === active}
						onmouseenter={() => (active = i)}
						class="group flex items-center gap-3 border-b px-3 py-2 text-sm last:border-b-0 {i ===
						active
							? 'bg-muted'
							: ''}"
					>
						<button
							type="button"
							onclick={() => go(item)}
							class="flex min-w-0 flex-1 items-center gap-3 text-left"
							title={item.game?.title || item.product.title}
						>
							<!-- The row's picture grows with the cursor: a thumbnail while
							     scanning, big enough to recognise once you settle on one. -->
							<ProductImage
								src={item.bgg?.thumbnail || item.product.image_url || ''}
								productId={item.product.id}
								alt=""
								eager
								fallbackText=""
								class="shrink-0 rounded transition-[width,height] duration-200 {i === active
									? 'size-20'
									: 'size-11'}"
							/>
							<span class="min-w-0 flex-1 space-y-0.5">
								<span class="block truncate font-medium">
									{item.game?.title || item.product.title}
								</span>
								<span
									class="flex items-center gap-1 text-xs whitespace-nowrap text-muted-foreground"
								>
									<span class="flex items-center gap-0.5">
										{#each shops.ids as id (id)}
											<span
												class="size-1.5 rounded-full"
												style="background:{storeColors.of(id)}"
												title={id}
												aria-hidden="true"
											></span>
										{/each}
									</span>
									{shops.label}
									{#if price(item) != null}· {inr(price(item))}{/if}
								</span>
							</span>
						</button>
						<button
							type="button"
							onclick={() => watchlist.toggle(item)}
							class="grid size-8 shrink-0 place-items-center rounded-full transition-colors {watched
								? 'text-rose-500'
								: 'text-muted-foreground hover:text-rose-500'}"
							title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
							aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
							aria-pressed={watched}
						>
							<Heart class="size-4" fill={watched ? 'currentColor' : 'none'} />
						</button>
					</li>
				{/each}
			</ul>
			<button
				type="button"
				onclick={submitAll}
				class="w-full border-t px-3 py-2 text-center text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
			>
				Show all results for “{q.trim()}”
			</button>
		</div>
	{/if}
</div>
