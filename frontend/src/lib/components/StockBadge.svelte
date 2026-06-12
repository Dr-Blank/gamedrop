<script>
	import { Badge } from '$lib/components/ui/badge';
	let { available = false, size = 'md' } = $props();
</script>

{#if available}
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
