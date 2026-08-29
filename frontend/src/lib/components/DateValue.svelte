<script>
	import {
		RELATIVE_UNITS,
		dateModeOf,
		formatRelative,
		parseRelative,
		todayISO
	} from '$lib/dateFilters.js';

	/** @type {{ value: any, label: string }} */
	let { value = $bindable(), label } = $props();

	const mode = $derived(dateModeOf(value));
	const parts = $derived(parseRelative(value) ?? { amount: 1, unit: 'd', dir: 'ago' });

	const MODES = [
		{ value: 'relative', label: 'ago / ahead' },
		{ value: 'now', label: 'now' },
		{ value: 'today', label: 'start of today' },
		{ value: 'exact', label: 'on date' }
	];

	function setMode(next) {
		if (next === 'relative') value = formatRelative(parts);
		else if (next === 'exact') value = todayISO();
		else value = next;
	}

	/** @param {Partial<{amount: number, unit: string, dir: string}>} patch */
	function edit(patch) {
		value = formatRelative({ ...parts, ...patch });
	}
</script>

<select
	value={mode}
	onchange={(e) => setMode(e.target.value)}
	aria-label="{label} mode"
	class="h-7 rounded border bg-background px-2 text-xs"
>
	{#each MODES as m (m.value)}
		<option value={m.value}>{m.label}</option>
	{/each}
</select>

{#if mode === 'relative'}
	<input
		type="number"
		min="0"
		step="1"
		value={parts.amount}
		oninput={(e) => edit({ amount: Number(e.target.value) })}
		aria-label="{label} amount"
		class="h-7 w-16 rounded border bg-background px-2 text-xs"
	/>
	<select
		value={parts.unit}
		onchange={(e) => edit({ unit: e.target.value })}
		aria-label="{label} unit"
		class="h-7 rounded border bg-background px-2 text-xs"
	>
		{#each RELATIVE_UNITS as unit (unit.value)}
			<option value={unit.value}>{unit.label}</option>
		{/each}
	</select>
	<select
		value={parts.dir}
		onchange={(e) => edit({ dir: e.target.value })}
		aria-label="{label} direction"
		class="h-7 rounded border bg-background px-2 text-xs"
	>
		<option value="ago">ago</option>
		<option value="ahead">from now</option>
	</select>
{:else if mode === 'exact'}
	<input
		type="date"
		bind:value
		aria-label={label}
		class="h-7 rounded border bg-background px-2 text-xs"
	/>
{/if}
