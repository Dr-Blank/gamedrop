<script>
	import { cn } from '$lib/utils.js';
	import { fetchProductImage } from '$lib/api.js';

	let {
		src = '',
		alt = '',
		class: className = '',
		/** When set and `src` is empty, lazily fetch + store this product's image. */
		productId = /** @type {number|null} */ (null),
		/** Tailwind sizing for the fallback emoji */
		fallbackText = '🎲'
	} = $props();

	let loaded = $state(false);
	let errored = $state(false);
	let el = $state(/** @type {HTMLDivElement | null} */ (null));
	let near = $state(false);
	let fetched = $state(''); // image url resolved on demand from the backend
	let tried = false;

	// Effective source: provided src wins, else whatever we fetched on demand.
	const effSrc = $derived(src || fetched);

	// On-demand: only attach the real src once the image scrolls near the viewport.
	$effect(() => {
		if (!el || near) return;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) {
					near = true;
					io.disconnect();
				}
			},
			{ rootMargin: '300px' }
		);
		io.observe(el);
		return () => io.disconnect();
	});

	// No stored image + near the viewport → fetch just this one (async, once).
	$effect(() => {
		if (!near || src || fetched || tried || productId == null) return;
		tried = true;
		fetchProductImage(productId)
			.then((res) => {
				if (res?.image_url) fetched = res.image_url;
			})
			.catch(() => {
				// Leave the emoji fallback in place; nothing else to do.
			});
	});

	// Reset state when the effective source changes.
	$effect(() => {
		effSrc;
		loaded = false;
		errored = false;
	});
</script>

<div
	bind:this={el}
	class={cn(
		'relative overflow-hidden bg-muted/30 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.06)] dark:bg-zinc-900 dark:shadow-[inset_0_0_28px_rgba(0,0,0,0.45)]',
		className
	)}
>
	{#if !loaded && !errored}
		<div class="absolute inset-0 animate-pulse bg-muted/60"></div>
	{/if}

	{#if effSrc && near && !errored}
		<img
			src={effSrc}
			{alt}
			loading="lazy"
			decoding="async"
			onload={() => (loaded = true)}
			onerror={() => (errored = true)}
			class="h-full w-full object-contain p-2 transition-opacity duration-500 {loaded
				? 'opacity-100'
				: 'opacity-0'}"
		/>
	{:else if errored || !effSrc}
		<div class="flex h-full w-full items-center justify-center text-4xl opacity-40">
			{fallbackText}
		</div>
	{/if}
</div>
