<script>
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { ArrowUp, ArrowDown, Plus, Trash2, X } from '@lucide/svelte';

	let {
		fields = /** @type {any[]} */ ([]),
		sorts = $bindable(/** @type {Array<{field:string,dir:string}>} */ ([])),
		onapply = /** @type {(()=>void)|null} */ (null)
	} = $props();

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
					<div class="flex items-center gap-1.5">
						<span class="w-4 text-center text-xs text-muted-foreground">{i + 1}</span>
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
				<button
					onclick={addSort}
					class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
				>
					<Plus class="size-3" /> Add sort
				</button>
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
