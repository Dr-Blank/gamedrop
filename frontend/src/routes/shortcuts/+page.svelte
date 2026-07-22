<script>
	import { SHORTCUT_CATALOG } from '$lib/shortcuts.svelte.js';
	import ShortcutList from '$lib/components/ShortcutList.svelte';
	import { Keyboard } from '@lucide/svelte';
</script>

<div class="max-w-2xl space-y-5">
	<div>
		<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
			<Keyboard class="size-6 text-primary" /> Keyboard shortcuts
		</h1>
		<p class="text-sm text-muted-foreground">
			Press <kbd class="rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-xs">?</kbd>
			anywhere for the shortcuts available on that page.
		</p>
	</div>

	<div class="rounded-xl border p-5">
		<ShortcutList list={SHORTCUT_CATALOG} />
	</div>

	<p class="text-sm text-muted-foreground">
		Sequences are typed one key after another: <kbd
			class="rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-xs">G</kbd
		>
		then
		<kbd class="rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-xs">W</kbd>
		opens the watchlist. Shortcuts stay out of the way while you are typing in a text field.
	</p>
</div>
