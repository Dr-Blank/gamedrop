<script>
	/** `?` help sheet, plus the chord hint that shows a half-typed sequence. */
	import { fly } from 'svelte/transition';
	import { shortcuts } from '$lib/shortcuts.svelte.js';
	import ShortcutList from './ShortcutList.svelte';
	import { Keyboard } from '@lucide/svelte';
</script>

{#if shortcuts.pending}
	<div
		class="fixed bottom-4 left-4 z-50 rounded-lg border bg-popover px-3 py-1.5 font-mono text-sm shadow-lg"
		transition:fly={{ y: 8, duration: 120 }}
	>
		{shortcuts.pending} …
	</div>
{/if}

{#if shortcuts.helpOpen}
	<!-- Backdrop is a real button: click-to-close needs to be reachable by
	     keyboard too, and Esc alone leaves screen-reader users no target. -->
	<button
		class="fixed inset-0 z-50 cursor-default bg-black/50 backdrop-blur-sm"
		aria-label="Close shortcuts"
		onclick={() => (shortcuts.helpOpen = false)}
		transition:fly={{ duration: 120 }}
	></button>
	<div class="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
		<div
			class="pointer-events-auto max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-xl border bg-background p-5 shadow-xl"
			role="dialog"
			tabindex="-1"
			aria-modal="true"
			aria-label="Keyboard shortcuts"
			transition:fly={{ y: 12, duration: 150 }}
		>
			<h2 class="mb-4 flex items-center gap-2 text-lg font-bold">
				<Keyboard class="size-5 text-primary" /> Keyboard shortcuts
			</h2>

			<!-- Live registrations only: what works on the page behind the sheet. -->
			<ShortcutList list={shortcuts.all} />

			<p class="mt-5 flex items-center justify-between gap-3 text-xs text-muted-foreground">
				<span>Press <kbd class="rounded border px-1 font-mono">Esc</kbd> to close.</span>
				<a href="/shortcuts" class="underline hover:text-foreground">Full reference</a>
			</p>
		</div>
	</div>
{/if}
