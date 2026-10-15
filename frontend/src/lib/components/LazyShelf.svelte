<script>
	import { shelfItems } from '$lib/api.js';
	import Shelf from './Shelf.svelte';

	/** A home shelf that fetches its own cards once it scrolls near the viewport. */
	let {
		shelf,
		icon = null,
		href = '',
		limit = 8,
		/** @type {import('svelte').Snippet<[any]>} */
		card,
		/** @type {import('svelte').Snippet} */
		skeleton,
		/** @type {import('svelte').Snippet | undefined} */
		actions = undefined
	} = $props();

	let el = $state(/** @type {HTMLDivElement | null} */ (null));
	let near = $state(typeof IntersectionObserver === 'undefined');
	let items = $state(/** @type {any[] | null} */ (null));

	$effect(() => {
		if (!el || near) return;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) {
					near = true;
					io.disconnect();
				}
			},
			{ rootMargin: '400px' }
		);
		io.observe(el);
		return () => io.disconnect();
	});

	$effect(() => {
		if (!near || items !== null) return;
		shelfItems(shelf.id, limit)
			.then((res) => (items = res))
			.catch(() => (items = []));
	});
</script>

<div bind:this={el}>
	<Shelf
		title={shelf.name}
		{icon}
		{href}
		items={items ?? []}
		loading={items === null}
		empty="Nothing here yet."
		{card}
		{skeleton}
		{actions}
	/>
</div>
