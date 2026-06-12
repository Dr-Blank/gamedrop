<script>
	import { cn } from '$lib/utils.js';
	let { class: className = '' } = $props();
</script>

<div class={cn('animate-pulse rounded-md bg-muted', className)}></div>
