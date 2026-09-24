<script>
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { ArrowUp, ArrowDown, Plus, Trash2, X, GitCompareArrows } from '@lucide/svelte';

	let {
		fields = /** @type {any[]} */ ([]),
		stores = /** @type {any[]} */ ([]),
		sorts = $bindable(/** @type {any[]} */ ([])),
		onapply = /** @type {(()=>void)|null} */ (null)
	} = $props();

	// A gap against this store means "against whichever other shop is
	// cheapest", which keeps working as shops are added.
	const ANY_OTHER = '*';

	/** A shop cannot be measured against itself. */
	function keepRivalDistinct(sort) {
		if (sort.store_b === sort.store_a) sort.store_b = ANY_OTHER;
	}

	// The orderings worth one click. Anything else is built below.
	const PRESETS = [
		{ label: 'Name A→Z', sort: { field: 'title', dir: 'asc' } },
		{ label: 'Name Z→A', sort: { field: 'title', dir: 'desc' } },
		{ label: 'Price low→high', sort: { field: 'price', dir: 'asc' } },
		{ label: 'Price high→low', sort: { field: 'price', dir: 'desc' } },
		{ label: 'In stock first', sort: { field: 'available', dir: 'desc' } },
		{ label: 'Biggest discount', sort: { field: 'discount_pct', dir: 'desc' } },
		{ label: 'Newest', sort: { field: 'first_seen', dir: 'desc' } }
	];

	const sortableFields = $derived(fields.filter((f) => f.sortable));
	const available = $derived(
		PRESETS.filter((p) => sortableFields.some((f) => f.name === p.sort.field))
	);

	/** @param {{field:string,dir:string}} sort */
	function isActive(sort) {
		return sorts.length === 1 && sorts[0].field === sort.field && sorts[0].dir === sort.dir;
	}

	function addGapSort() {
		const first = stores[0]?.id;
		if (!first) return;
		sorts = [
			...sorts,
			{
				type: 'store_gap',
				store_a: first,
				store_b: ANY_OTHER,
				mode: 'abs',
				stock: 'in_stock',
				dir: 'asc'
			}
		];
	}

	/** @param {string} id */
	function storeName(id) {
		return stores.find((s) => s.id === id)?.name ?? id;
	}

	/** @param {{field:string,dir:string}} sort */
	function pick(sort) {
		sorts = isActive(sort) ? [] : [{ ...sort }];
		onapply?.();
	}

	// Rebuilt rather than mutated so the list updates however it was handed in.
	function addSort() {
		const used = new Set(sorts.map((s) => s.field));
		const first = sortableFields.find((f) => !used.has(f.name));
		if (first) sorts = [...sorts, { field: first.name, dir: 'asc' }];
	}

	function removeSort(/** @type {number} */ i) {
		sorts = sorts.filter((_, k) => k !== i);
	}

	function moveSort(/** @type {number} */ i, /** @type {number} */ dir) {
		const j = i + dir;
		if (j < 0 || j >= sorts.length) return;
		const next = [...sorts];
		[next[i], next[j]] = [next[j], next[i]];
		sorts = next;
	}

	function clear() {
		sorts = [];
		onapply?.();
	}
</script>

<Card.Root>
	<Card.Content class="space-y-4 p-4">
		<div class="space-y-2">
			<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Sort by</p>
			<div class="flex flex-wrap gap-1.5">
				{#each available as preset (preset.label)}
					<button
						onclick={() => pick(preset.sort)}
						aria-pressed={isActive(preset.sort)}
						class="rounded-full border px-3 py-1 text-xs transition-colors {isActive(preset.sort)
							? 'border-primary bg-primary text-primary-foreground'
							: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
					>
						{preset.label}
					</button>
				{/each}
			</div>
		</div>

		<div class="space-y-2">
			<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">
				Sort priority (first = primary)
			</p>
			<div class="space-y-1.5">
				{#each sorts as sort, i (i)}
					<div class="flex flex-wrap items-center gap-1.5">
						<span class="w-4 text-center text-xs text-muted-foreground">{i + 1}</span>
						{#if sort.type === 'store_gap'}
							<span class="text-xs text-muted-foreground">Gap</span>
							<select
								bind:value={sort.store_a}
								onchange={() => keepRivalDistinct(sort)}
								aria-label="Gap store"
								class="h-7 rounded border bg-background px-2 text-xs"
							>
								{#each stores as store (store.id)}
									<option value={store.id}>{store.name}</option>
								{/each}
							</select>
							<span class="text-xs text-muted-foreground">vs</span>
							<select
								bind:value={sort.store_b}
								aria-label="Gap rival store"
								class="h-7 rounded border bg-background px-2 text-xs"
							>
								<option value={ANY_OTHER}>cheapest other shop</option>
								{#each stores.filter((st) => st.id !== sort.store_a) as store (store.id)}
									<option value={store.id}>{store.name}</option>
								{/each}
							</select>
							<select
								bind:value={sort.mode}
								aria-label="Gap unit"
								class="h-7 rounded border bg-background px-2 text-xs"
							>
								<option value="abs">₹</option>
								<option value="pct">%</option>
							</select>
							<select
								bind:value={sort.stock}
								aria-label="Gap stock scope"
								class="h-7 rounded border bg-background px-2 text-xs"
							>
								<option value="in_stock">in stock only</option>
								<option value="any">stocked or not</option>
							</select>
							<select
								bind:value={sort.dir}
								aria-label="Sort direction"
								title="Ascending puts the biggest saving at {storeName(sort.store_a)} first"
								class="h-7 w-28 rounded border bg-background px-2 text-xs"
							>
								<option value="asc">↑ cheapest here</option>
								<option value="desc">↓ dearest here</option>
							</select>
						{:else}
							<select
								bind:value={sort.field}
								aria-label="Sort field"
								class="h-7 flex-1 rounded border bg-background px-2 text-xs"
							>
								{#each sortableFields as f}
									<option value={f.name}>{f.label}</option>
								{/each}
							</select>
							<select
								bind:value={sort.dir}
								aria-label="Sort direction"
								class="h-7 w-24 rounded border bg-background px-2 text-xs"
							>
								<option value="asc">↑ asc</option>
								<option value="desc">↓ desc</option>
							</select>
						{/if}
						<button
							onclick={() => moveSort(i, -1)}
							disabled={i === 0}
							aria-label="Move sort up"
							class="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
						>
							<ArrowUp class="size-3" />
						</button>
						<button
							onclick={() => moveSort(i, 1)}
							disabled={i === sorts.length - 1}
							aria-label="Move sort down"
							class="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
						>
							<ArrowDown class="size-3" />
						</button>
						<button
							onclick={() => removeSort(i)}
							aria-label="Remove sort"
							class="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
						>
							<Trash2 class="size-3" />
						</button>
					</div>
				{/each}
				<div class="flex gap-1.5">
					<button
						onclick={addSort}
						class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
					>
						<Plus class="size-3" /> Add sort
					</button>
					{#if stores.length > 1}
						<button
							onclick={addGapSort}
							title="Order by how far one shop's price sits from another's"
							class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
						>
							<GitCompareArrows class="size-3" /> Add store gap
						</button>
					{/if}
				</div>
			</div>
		</div>

		<div class="flex gap-2 pt-1">
			<Button onclick={() => onapply?.()}>Apply</Button>
			<Button variant="ghost" onclick={clear} disabled={sorts.length === 0}>
				<X class="size-4" /> Clear
			</Button>
		</div>
	</Card.Content>
</Card.Root>
