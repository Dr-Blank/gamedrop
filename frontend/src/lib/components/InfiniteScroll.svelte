<script>
	/**
	 * Sentinel that pulls the next page when it scrolls into view.
	 *
	 * Pages keep owning their own paging state — this only decides *when* to
	 * ask for more. `rootMargin` fires the request while the sentinel is still
	 * below the fold so the next batch is usually there before the user
	 * reaches the end of the current one.
	 */
	import { tick } from 'svelte';
	import { Loader2 } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';

	let {
		hasMore = false,
		loading = false,
		onload,
		remaining = null,
		rootMargin = '800px'
	} = $props();

	let sentinel = $state(null);
	// Assume auto-loading whenever the browser can do it: starting at false
	// flashes the fallback button between first paint and the effect running.
	let auto = $state(typeof IntersectionObserver !== 'undefined');
	let observer = null;
	let busy = false; // guards against a second fire before `loading` flips

	async function fire() {
		if (busy || loading || !hasMore) return;
		busy = true;
		try {
			await onload?.();
		} finally {
			busy = false;
			// Re-arm: when the viewport is taller than the new batch the sentinel
			// never leaves the screen, and an observer only fires on a crossing.
			await tick();
			if (observer && sentinel) {
				observer.unobserve(sentinel);
				observer.observe(sentinel);
			}
		}
	}

	$effect(() => {
		if (!sentinel || typeof IntersectionObserver === 'undefined') return;
		observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) fire();
			},
			{ rootMargin }
		);
		observer.observe(sentinel);
		return () => {
			observer?.disconnect();
			observer = null;
		};
	});
</script>

{#if hasMore}
	<div bind:this={sentinel} class="flex justify-center py-6" aria-live="polite">
		{#if loading}
			<span class="flex items-center gap-2 text-sm text-muted-foreground">
				<Loader2 class="size-4 animate-spin" />
				Loading{remaining ? ` ${remaining} more` : ' more'}…
			</span>
		{:else if !auto}
			<!-- No IntersectionObserver: fall back to the manual control. -->
			<Button variant="outline" onclick={fire}>Load more</Button>
		{/if}
	</div>
{/if}
