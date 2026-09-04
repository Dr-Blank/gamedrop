<script>
	import { Button } from '$lib/components/ui/button';
	import MarkdownNote from './MarkdownNote.svelte';
	import { inr } from '$lib/priceFormat.svelte.js';
	import { PRIORITIES } from '$lib/cartView.js';
	import { Minus, Plus, Target } from '@lucide/svelte';

	/** @type {{ item: any, onpatch: (body: any) => void }} */
	let { item, onpatch } = $props();

	let editingMax = $state(false);
	let maxInput = $state('');

	function openMax() {
		maxInput = item.max_price != null ? String(item.max_price) : '';
		editingMax = true;
	}

	function saveMax() {
		editingMax = false;
		onpatch(maxInput ? { max_price: Number(maxInput) } : { clear_max_price: true });
	}
</script>

<div class="space-y-3">
	<div class="flex flex-wrap gap-1">
		{#each PRIORITIES as p (p.id)}
			<button
				onclick={() => onpatch({ priority: p.id })}
				aria-pressed={item.priority === p.id}
				class="rounded-full border px-2.5 py-0.5 text-xs transition-colors {item.priority === p.id
					? 'border-primary bg-primary/10 font-medium text-foreground'
					: 'text-muted-foreground hover:border-primary/50 hover:text-foreground'}"
			>
				{p.label}
			</button>
		{/each}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<div class="flex items-center gap-1 rounded-md border">
			<button
				class="grid size-7 place-items-center text-muted-foreground hover:text-foreground disabled:opacity-40"
				disabled={item.quantity <= 1}
				onclick={() => onpatch({ quantity: item.quantity - 1 })}
				aria-label="Decrease quantity"
			>
				<Minus class="size-3" />
			</button>
			<span class="min-w-4 text-center text-xs tabular-nums">{item.quantity}</span>
			<button
				class="grid size-7 place-items-center text-muted-foreground hover:text-foreground"
				onclick={() => onpatch({ quantity: item.quantity + 1 })}
				aria-label="Increase quantity"
			>
				<Plus class="size-3" />
			</button>
		</div>

		{#if editingMax}
			<input
				type="number"
				bind:value={maxInput}
				placeholder="No limit"
				aria-label="Buy at or below"
				class="h-7 w-24 rounded-md border bg-background px-2 text-xs focus:ring-2 focus:ring-ring focus:outline-none"
			/>
			<Button size="sm" onclick={saveMax}>Set</Button>
		{:else}
			<button
				onclick={openMax}
				class="inline-flex items-center gap-1 rounded-full border border-dashed px-2 py-0.5 text-xs text-muted-foreground transition hover:border-primary hover:text-foreground"
				title="Buy-at ceiling for this row"
			>
				<Target class="size-3" />
				{item.max_price != null ? inr(item.max_price) : 'no limit'}
			</button>
		{/if}
	</div>

	<MarkdownNote
		value={item.note}
		placeholder="Why this one? Editions, expansions, who it's for…"
		onsave={(next) => onpatch({ note: next })}
	/>
</div>
