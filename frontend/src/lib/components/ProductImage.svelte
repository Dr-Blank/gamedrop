<script>
	import { cn } from '$lib/utils.js';

	let {
		src = '',
		alt = '',
		class: className = '',
		/** Tailwind sizing for the fallback emoji */
		fallbackText = '🎲'
	} = $props();

	let loaded = $state(false);
	let errored = $state(false);
	let el = $state(/** @type {HTMLDivElement | null} */ (null));
	let near = $state(false);

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

	// Reset state when src changes.
	$effect(() => {
		src;
		loaded = false;
		errored = false;
	});
</script>

<div bind:this={el} class={cn('relative overflow-hidden bg-muted/40', className)}>
	{#if !loaded && !errored}
		<div class="absolute inset-0 animate-pulse bg-muted/60"></div>
	{/if}

	{#if src && near && !errored}
		<img
			{src}
			{alt}
			loading="lazy"
			decoding="async"
			onload={() => (loaded = true)}
			onerror={() => (errored = true)}
			class="h-full w-full object-contain p-2 transition-opacity duration-500 {loaded
				? 'opacity-100'
				: 'opacity-0'}"
		/>
	{:else if errored || !src}
		<div class="flex h-full w-full items-center justify-center text-4xl opacity-40">
			{fallbackText}
		</div>
	{/if}
</div>
