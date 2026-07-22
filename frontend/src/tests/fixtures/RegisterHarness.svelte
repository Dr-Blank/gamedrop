<script>
	/** Mirrors how a page registers its shortcuts: inside an $effect. */
	import { shortcuts } from '$lib/shortcuts.svelte.js';

	let { list = [], handlers = {} } = $props();

	$effect(() => shortcuts.register(list, handlers));
</script>

<div data-testid="harness"></div>
