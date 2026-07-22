<script>
	import { fly } from 'svelte/transition';
	import { MoreVertical, ArrowUp, ArrowDown, EyeOff, GripVertical } from '@lucide/svelte';

	/**
	 * Per-shelf quick actions on the home page. Move up/down saves immediately,
	 * so reordering one shelf never needs the full reorder mode.
	 */
	let { canMoveUp = true, canMoveDown = true, onmoveup, onmovedown, onhide, onreorder } = $props();

	let open = $state(false);

	function toggle(e) {
		e.stopPropagation();
		open = !open;
	}

	/** @param {() => void} action */
	function run(action) {
		open = false;
		action();
	}
</script>

<svelte:window onclick={() => (open = false)} />

<div class="relative">
	<button
		onclick={toggle}
		class="grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
		aria-label="Shelf options"
		aria-haspopup="menu"
		aria-expanded={open}
	>
		<MoreVertical class="size-4" />
	</button>

	{#if open}
		<div
			transition:fly={{ y: -6, duration: 120 }}
			onclick={(e) => e.stopPropagation()}
			role="menu"
			tabindex="-1"
			onkeydown={(e) => e.key === 'Escape' && (open = false)}
			class="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-xl border bg-popover py-1 shadow-lg"
		>
			<button
				role="menuitem"
				disabled={!canMoveUp}
				onclick={() => run(onmoveup)}
				class="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-40"
			>
				<ArrowUp class="size-4 text-muted-foreground" /> Move up
			</button>
			<button
				role="menuitem"
				disabled={!canMoveDown}
				onclick={() => run(onmovedown)}
				class="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-40"
			>
				<ArrowDown class="size-4 text-muted-foreground" /> Move down
			</button>
			<div class="my-1 border-t"></div>
			<button
				role="menuitem"
				onclick={() => run(onreorder)}
				class="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted"
			>
				<GripVertical class="size-4 text-muted-foreground" /> Edit shelves
			</button>
			<button
				role="menuitem"
				onclick={() => run(onhide)}
				class="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted"
			>
				<EyeOff class="size-4 text-muted-foreground" /> Hide shelf
			</button>
		</div>
	{/if}
</div>
