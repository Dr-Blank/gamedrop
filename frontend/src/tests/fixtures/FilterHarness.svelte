<script>
	import FilterGroup from '$lib/components/FilterGroup.svelte';

	let {
		fields = [],
		stores = [],
		initial = { type: 'group', op: 'and', conditions: [] },
		onstate
	} = $props();
	let group = $state(initial);
	$effect(() => onstate?.(group));
</script>

<FilterGroup bind:group {fields} {stores} />
