<script>
	import { Badge } from '$lib/components/ui/badge';
	let { available = false, preorder = false, size = 'md' } = $props();
</script>

{#if available && preorder}
	<Badge
		class="gap-1 border-amber-500/25 bg-amber-500/15 text-amber-600 dark:text-amber-400 {size ===
		'sm'
			? 'text-[0.7rem]'
			: ''}"
	>
		<span class="size-1.5 rounded-full bg-amber-500"></span>
		Pre-order
	</Badge>
{:else if available}
	<Badge
		class="gap-1 border-green-500/25 bg-green-500/15 text-green-600 dark:text-green-400 {size ===
		'sm'
			? 'text-[0.7rem]'
			: ''}"
	>
		<span class="size-1.5 rounded-full bg-green-500"></span>
		In stock
	</Badge>
{:else}
	<Badge variant="destructive" class="gap-1 {size === 'sm' ? 'text-[0.7rem]' : ''}">
		<span class="size-1.5 rounded-full bg-destructive"></span>
		Out of stock
	</Badge>
{/if}
