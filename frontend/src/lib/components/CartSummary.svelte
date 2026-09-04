<script>
	import { Button } from '$lib/components/ui/button';
	import { inr } from '$lib/priceFormat.svelte.js';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { basketShares } from '$lib/cartView.js';
	import { Wallet, Store, Sparkles, PackageX, AlertTriangle } from '@lucide/svelte';

	/**
	 * What the cart costs and how it splits. The per-shop baskets are the point:
	 * one order per shop is what actually gets placed, so shipping and free-
	 * delivery thresholds are decided on these numbers, not on the grand total.
	 *
	 * @type {{
	 *   summary: any,
	 *   switches: any[],
	 *   onbudget: (amount: number|null) => void,
	 *   onswitchall: () => void
	 * }}
	 */
	let { summary, switches = [], onbudget, onswitchall } = $props();

	let budgetDraft = $state('');
	let editingBudget = $state(false);

	const baskets = $derived(basketShares(summary));
	const budget = $derived(summary?.budget ?? null);
	const spent = $derived(summary?.total ?? 0);
	const overBudget = $derived(budget != null && spent > budget);
	const usedPct = $derived(budget ? Math.min(100, (spent / budget) * 100) : 0);
	const switchTotal = $derived(switches.reduce((sum, s) => sum + s.saves, 0));

	function openBudget() {
		budgetDraft = budget != null ? String(budget) : '';
		editingBudget = true;
	}

	function saveBudget() {
		const value = budgetDraft.trim();
		onbudget(value ? parseFloat(value) : null);
		editingBudget = false;
	}
</script>

<div class="space-y-3 rounded-xl border bg-card p-4">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<p class="text-xs tracking-wide text-muted-foreground uppercase">Cart total</p>
			<p class="text-2xl font-semibold tabular-nums">{inr(spent)}</p>
			<p class="text-xs text-muted-foreground">
				{summary.count} game{summary.count === 1 ? '' : 's'}
				{#if summary.unavailable > 0}
					· {inr(summary.in_stock_total)} buyable now
				{/if}
			</p>
		</div>

		<div class="text-right">
			{#if editingBudget}
				<div class="flex items-center gap-1">
					<input
						bind:value={budgetDraft}
						onkeydown={(e) => e.key === 'Enter' && saveBudget()}
						placeholder="Budget ₹"
						aria-label="Budget"
						class="h-8 w-28 rounded-md border bg-background px-2 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
					/>
					<Button size="sm" onclick={saveBudget}>Set</Button>
				</div>
			{:else}
				<button
					onclick={openBudget}
					class="inline-flex items-center gap-1.5 rounded-full border border-dashed px-3 py-1 text-sm text-muted-foreground transition hover:border-primary hover:text-foreground"
				>
					<Wallet class="size-3.5" />
					{budget != null ? `Budget ${inr(budget)}` : 'Set a budget'}
				</button>
			{/if}
			{#if budget != null}
				<p
					class="mt-1 text-xs tabular-nums {overBudget
						? 'text-rose-500'
						: 'text-green-600 dark:text-green-400'}"
				>
					{overBudget
						? `${inr(Math.abs(summary.budget_remaining))} over`
						: `${inr(summary.budget_remaining)} left`}
				</p>
			{/if}
		</div>
	</div>

	{#if budget != null}
		<div class="h-2 overflow-hidden rounded-full bg-muted">
			<div
				class="h-full rounded-full transition-all {overBudget ? 'bg-rose-500' : 'bg-primary'}"
				style="width:{usedPct}%"
			></div>
		</div>
	{/if}

	<!-- one bar, one order per shop -->
	{#if baskets.length > 0}
		<div class="space-y-1.5">
			<p class="flex items-center gap-1 text-xs text-muted-foreground">
				<Store class="size-3.5" />
				{baskets.length} order{baskets.length === 1 ? '' : 's'} to place
			</p>
			<div class="flex h-2 overflow-hidden rounded-full">
				{#each baskets as basket (basket.store_id)}
					<div
						class="h-full"
						style="width:{basket.share * 100}%; background:{storeColors.of(basket.store_id)}"
						title="{basket.store_id}: {inr(basket.total)}"
					></div>
				{/each}
			</div>
			<div class="flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem] text-muted-foreground">
				{#each baskets as basket (basket.store_id)}
					<span class="inline-flex items-center gap-1">
						<span class="size-1.5 rounded-full" style="background:{storeColors.of(basket.store_id)}"
						></span>
						{basket.store_id}
						<span class="tabular-nums">{inr(basket.total)}</span>
						<span class="opacity-60">({basket.count})</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}

	<div class="flex flex-wrap items-center gap-3 text-xs">
		{#if summary.unavailable > 0}
			<span class="inline-flex items-center gap-1 text-muted-foreground">
				<PackageX class="size-3.5" />
				{summary.unavailable} not buyable right now
			</span>
		{/if}
		{#if summary.over_max > 0}
			<span class="inline-flex items-center gap-1 text-amber-600">
				<AlertTriangle class="size-3.5" />
				{summary.over_max} above your limit
			</span>
		{/if}
	</div>

	{#if switchTotal > 0}
		<div
			class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2"
		>
			<p class="flex items-center gap-1.5 text-xs text-green-700 dark:text-green-400">
				<Sparkles class="size-3.5" />
				{switches.length} row{switches.length === 1 ? '' : 's'} cost
				{inr(switchTotal)} more than the cheapest shop that has them.
			</p>
			<Button size="sm" onclick={onswitchall}>Save {inr(switchTotal)}</Button>
		</div>
	{/if}
</div>
