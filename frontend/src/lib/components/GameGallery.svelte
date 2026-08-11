<script>
	import ProductImage from './ProductImage.svelte';
	import { ChevronLeft, ChevronRight } from '@lucide/svelte';

	let {
		images = /** @type {Array<{url:string, store_id:string}>} */ ([]),
		primary = /** @type {string} */ (''),
		alt = ''
	} = $props();

	// The primary image (BGG art, or this listing's own) leads; store photos
	// follow, deduped, so a group where every shop uses the same photo shows one.
	const slides = $derived.by(() => {
		const out = [];
		const seen = new Set();
		if (primary) {
			out.push({ url: primary, store_id: '' });
			seen.add(primary);
		}
		for (const img of images ?? []) {
			if (!img.url || seen.has(img.url)) continue;
			seen.add(img.url);
			out.push(img);
		}
		return out;
	});

	let index = $state(0);
	const current = $derived(slides[Math.min(index, Math.max(slides.length - 1, 0))] ?? null);

	function step(delta) {
		if (!slides.length) return;
		index = (index + delta + slides.length) % slides.length;
	}
</script>

<div class="group/gallery relative">
	<ProductImage src={current?.url ?? ''} {alt} class="aspect-square w-full" />

	{#if slides.length > 1}
		<button
			onclick={() => step(-1)}
			aria-label="Previous image"
			class="absolute top-1/2 left-1 grid size-7 -translate-y-1/2 place-items-center rounded-full bg-background/80 text-muted-foreground opacity-0 shadow-sm backdrop-blur transition group-hover/gallery:opacity-100 hover:text-foreground"
		>
			<ChevronLeft class="size-4" />
		</button>
		<button
			onclick={() => step(1)}
			aria-label="Next image"
			class="absolute top-1/2 right-1 grid size-7 -translate-y-1/2 place-items-center rounded-full bg-background/80 text-muted-foreground opacity-0 shadow-sm backdrop-blur transition group-hover/gallery:opacity-100 hover:text-foreground"
		>
			<ChevronRight class="size-4" />
		</button>

		<div class="absolute inset-x-0 bottom-1.5 flex items-center justify-center gap-1.5">
			{#each slides as slide, i}
				<button
					onclick={() => (index = i)}
					aria-label="Image {i + 1}{slide.store_id ? ` from ${slide.store_id}` : ''}"
					aria-current={i === index}
					class="size-1.5 rounded-full transition-all {i === index
						? 'w-4 bg-foreground'
						: 'bg-foreground/30 hover:bg-foreground/60'}"
				></button>
			{/each}
		</div>

		{#if current?.store_id}
			<span
				class="absolute top-1.5 left-1.5 rounded-full bg-background/80 px-2 py-0.5 text-[0.65rem] text-muted-foreground backdrop-blur"
			>
				{current.store_id}
			</span>
		{/if}
	{/if}
</div>
