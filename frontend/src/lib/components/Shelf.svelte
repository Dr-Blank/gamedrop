<script>
	import { Button } from '$lib/components/ui/button';
	import { ChevronLeft, ChevronRight, ArrowRight } from '@lucide/svelte';

	let {
		title,
		href = '',
		icon = null,
		items = [],
		empty = 'Nothing here yet.',
		loading = false,
		/** @type {import('svelte').Snippet<[any]>} */
		card,
		/** @type {import('svelte').Snippet} */
		skeleton,
		/** Extra header controls, rendered after the scroll arrows.
		 * @type {import('svelte').Snippet | undefined} */
		actions = undefined
	} = $props();

	let scroller = $state(/** @type {HTMLDivElement | null} */ (null));
	let canLeft = $state(false);
	let canRight = $state(false);

	function update() {
		if (!scroller) return;
		canLeft = scroller.scrollLeft > 4;
		canRight = scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 4;
	}

	/** @param {number} dir */
	function scroll(dir) {
		scroller?.scrollBy({ left: dir * scroller.clientWidth * 0.8, behavior: 'smooth' });
	}

	$effect(() => {
		items;
		requestAnimationFrame(update);
	});
</script>

<section class="space-y-3">
	<div class="flex items-end justify-between gap-3">
		<h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight">
			{#if icon}{@const Icon = icon}<Icon class="size-5 text-primary" />{/if}
			{title}
		</h2>
		<div class="flex items-center gap-1">
			{#if href}
				<Button variant="ghost" size="sm" {href} class="text-muted-foreground">
					See all <ArrowRight class="size-3.5" />
				</Button>
			{/if}
			<div class="hidden gap-1 sm:flex">
				<Button
					variant="outline"
					size="icon-sm"
					onclick={() => scroll(-1)}
					disabled={!canLeft}
					aria-label="Scroll left"
				>
					<ChevronLeft class="size-4" />
				</Button>
				<Button
					variant="outline"
					size="icon-sm"
					onclick={() => scroll(1)}
					disabled={!canRight}
					aria-label="Scroll right"
				>
					<ChevronRight class="size-4" />
				</Button>
			</div>
			{@render actions?.()}
		</div>
	</div>

	{#if loading}
		<div class="flex gap-3 overflow-hidden">
			{#each Array(6) as _}
				<div class="w-[170px] shrink-0 sm:w-[190px]">
					{@render skeleton?.()}
				</div>
			{/each}
		</div>
	{:else if items.length === 0}
		<p class="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
			{empty}
		</p>
	{:else}
		<div
			bind:this={scroller}
			onscroll={update}
			class="-mx-1 flex snap-x snap-mandatory [scrollbar-width:none] gap-3 overflow-x-auto scroll-smooth px-1 pb-2 [&::-webkit-scrollbar]:hidden"
		>
			{#each items as item}
				<div class="w-[170px] shrink-0 snap-start sm:w-[190px]">
					{@render card(item)}
				</div>
			{/each}
		</div>
	{/if}
</section>
