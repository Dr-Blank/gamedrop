<script>
	import { storeColors } from '$lib/storeColors.svelte.js';

	let {
		stores = /** @type {string[]} */ ([]),
		hidden = /** @type {Set<string>} */ (new Set()),
		ontoggle = /** @type {((id: string) => void)|null} */ (null)
	} = $props();
</script>

<div class="flex flex-wrap items-center justify-center gap-2">
	{#each stores as id}
		{@const off = hidden.has(id)}
		<button
			onclick={() => ontoggle?.(id)}
			class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-muted/50 {off
				? 'text-muted-foreground/60'
				: 'text-foreground'}"
			aria-pressed={!off}
		>
			<span
				class="size-2 rounded-full"
				style:background-color={off ? 'transparent' : storeColors.of(id)}
				style:box-shadow="inset 0 0 0 1.5px {storeColors.of(id)}"
			></span>
			<span class={off ? 'line-through' : ''}>{storeColors.name(id)}</span>
		</button>
	{/each}
</div>
