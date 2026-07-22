<script>
	/** Grouped shortcut table. Shared by the `?` sheet and the /shortcuts page. */
	import { keyLabels } from '$lib/shortcuts.svelte.js';

	let { list = [] } = $props();

	// Actions with several bindings (search: / , ⌘K, Ctrl+F) collapse to one row.
	const groups = $derived.by(() => {
		/** @type {Map<string, Map<string, string[]>>} */
		const out = new Map();
		for (const s of list) {
			if (!out.has(s.group)) out.set(s.group, new Map());
			const rows = out.get(s.group);
			rows.set(s.label, [...(rows.get(s.label) ?? []), s.keys]);
		}
		return [...out].map(([group, rows]) => [group, [...rows]]);
	});
</script>

<div class="space-y-5">
	{#each groups as [group, rows]}
		<div>
			<p class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
				{group}
			</p>
			<ul class="space-y-1.5">
				{#each rows as [label, bindings]}
					<li class="flex items-center justify-between gap-4 text-sm">
						<span>{label}</span>
						<span class="flex shrink-0 flex-wrap items-center justify-end gap-1">
							{#each bindings as keys, i}
								{#if i > 0}<span class="text-xs text-muted-foreground">or</span>{/if}
								{#each keyLabels(keys) as part}
									<kbd class="rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-xs"
										>{part}</kbd
									>
								{/each}
							{/each}
						</span>
					</li>
				{/each}
			</ul>
		</div>
	{/each}
</div>
