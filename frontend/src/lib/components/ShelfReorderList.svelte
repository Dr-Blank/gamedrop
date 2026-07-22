<script>
	import { flip } from 'svelte/animate';
	import { GripVertical, ArrowUp, ArrowDown, X, Plus, Check, Wand2 } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { shelfIcon } from '$lib/shelfIcons.js';

	/**
	 * Home page reorder mode: every shelf collapses to a single row so the whole
	 * running order fits on one screen. Order changes stay local and are saved
	 * when the user leaves the mode.
	 *
	 * Rows stay still at rest — the mode header, tinted surface and grip handles
	 * already say "editable". Motion is spent on the reorder itself (FLIP) so a
	 * move is legible instead of a jump.
	 *
	 * @type {{
	 *   shelves: any[],
	 *   hidden?: any[],
	 *   onhide: (shelf: any) => void,
	 *   onunhide: (shelf: any) => void,
	 *   ondone: () => void
	 * }}
	 */
	let { shelves = $bindable(), hidden = [], onhide, onunhide, ondone } = $props();

	let dragIndex = $state(/** @type {number | null} */ (null));

	// Respect the OS motion setting — FLIP is JS-driven, so the global
	// prefers-reduced-motion CSS override in layout.css doesn't reach it.
	const reduceMotion =
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	const flipMs = reduceMotion ? 0 : 180;

	/** @param {number} from @param {number} to */
	function move(from, to) {
		if (to < 0 || to >= shelves.length || from === to) return;
		const next = [...shelves];
		const [row] = next.splice(from, 1);
		next.splice(to, 0, row);
		shelves = next;
	}

	/** @param {number} index */
	function dragOver(index) {
		if (dragIndex === null || dragIndex === index) return;
		move(dragIndex, index);
		dragIndex = index;
	}
</script>

<section class="space-y-3">
	<div class="flex items-center justify-between gap-3">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Edit shelves</h2>
			<p class="text-sm text-muted-foreground">
				Drag the handle or use the arrows. Changes save when you're done.
			</p>
		</div>
		<Button onclick={ondone}>
			<Check class="size-4" /> Done
		</Button>
	</div>

	<ul class="space-y-2 rounded-xl bg-muted/40 p-2">
		{#each shelves as shelf, i (shelf.id)}
			{@const Icon = shelfIcon(shelf.icon)}
			<li
				draggable="true"
				animate:flip={{ duration: flipMs }}
				ondragstart={() => (dragIndex = i)}
				ondragover={(e) => {
					e.preventDefault();
					dragOver(i);
				}}
				ondragend={() => (dragIndex = null)}
				ondrop={(e) => e.preventDefault()}
				class="flex cursor-grab items-center gap-2 rounded-xl border bg-card p-3 transition-shadow hover:border-primary/40 hover:shadow-sm active:cursor-grabbing"
				class:opacity-50={dragIndex === i}
				class:ring-2={dragIndex === i}
				class:ring-primary={dragIndex === i}
				class:shadow-lg={dragIndex === i}
			>
				<GripVertical class="size-5 shrink-0 text-muted-foreground" />
				<Icon class="size-4 shrink-0 text-primary" />
				<span class="min-w-0 flex-1 truncate text-sm font-medium">{shelf.name}</span>

				<Button
					variant="outline"
					size="icon-sm"
					disabled={i === 0}
					onclick={() => move(i, i - 1)}
					aria-label={`Move ${shelf.name} up`}
				>
					<ArrowUp class="size-4" />
				</Button>
				<Button
					variant="outline"
					size="icon-sm"
					disabled={i === shelves.length - 1}
					onclick={() => move(i, i + 1)}
					aria-label={`Move ${shelf.name} down`}
				>
					<ArrowDown class="size-4" />
				</Button>
				<Button
					variant="ghost"
					size="icon-sm"
					onclick={() => onhide(shelf)}
					aria-label={`Remove ${shelf.name} from home`}
					class="text-muted-foreground hover:text-destructive"
				>
					<X class="size-4" />
				</Button>
			</li>
		{/each}
	</ul>

	{#if shelves.length === 0}
		<p class="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
			No shelves on your home page. Add one below.
		</p>
	{/if}

	<div class="space-y-2 rounded-xl border border-dashed p-3">
		<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Add a shelf</p>
		<div class="flex flex-wrap items-center gap-2">
			{#each hidden as shelf (shelf.id)}
				{@const Icon = shelfIcon(shelf.icon)}
				<button
					onclick={() => onunhide(shelf)}
					class="flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors hover:bg-muted"
				>
					<Plus class="size-3.5 text-muted-foreground" />
					<Icon class="size-3.5 text-primary" />
					{shelf.name}
				</button>
			{/each}
			<Button href="/browse" variant="outline" size="sm">
				<Wand2 class="size-4" /> Build new shelf
			</Button>
		</div>
		{#if hidden.length === 0}
			<p class="text-sm text-muted-foreground">
				Every shelf is already on your home page. Build a new one from a browse filter.
			</p>
		{/if}
	</div>
</section>
