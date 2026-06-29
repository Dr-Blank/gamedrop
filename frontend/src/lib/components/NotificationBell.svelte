<script>
	import { fly } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import {
		Bell,
		TrendingDown,
		TrendingUp,
		Package,
		PackageX,
		Crosshair,
		CheckCheck,
		ArrowRight
	} from '@lucide/svelte';
	import { notifications } from '$lib/notifications.svelte.js';

	let open = $state(false);
	let loading = $state(false);

	/** @type {any[]} */
	let items = $state([]);

	const KIND = {
		price_drop: {
			icon: TrendingDown,
			bg: 'bg-emerald-100 dark:bg-emerald-900/40',
			color: 'text-emerald-600 dark:text-emerald-400',
			label: 'Price drop'
		},
		back_in_stock: {
			icon: Package,
			bg: 'bg-blue-100 dark:bg-blue-900/40',
			color: 'text-blue-600 dark:text-blue-400',
			label: 'Back in stock'
		},
		target_reached: {
			icon: Crosshair,
			bg: 'bg-orange-100 dark:bg-orange-900/40',
			color: 'text-orange-600 dark:text-orange-400',
			label: 'Target hit'
		},
		price_increase: {
			icon: TrendingUp,
			bg: 'bg-rose-100 dark:bg-rose-900/40',
			color: 'text-rose-600 dark:text-rose-400',
			label: 'Price increase'
		},
		out_of_stock: {
			icon: PackageX,
			bg: 'bg-zinc-100 dark:bg-zinc-800/60',
			color: 'text-zinc-500 dark:text-zinc-400',
			label: 'Out of stock'
		}
	};

	function reltime(ts) {
		const diff = Date.now() - new Date(ts + 'Z').getTime();
		if (diff < 60_000) return 'just now';
		if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
		if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
		const d = Math.floor(diff / 86_400_000);
		if (d === 1) return 'yesterday';
		if (d < 7) return `${d}d ago`;
		return new Date(ts + 'Z').toLocaleDateString();
	}

	async function toggle(e) {
		e.stopPropagation();
		if (!open) {
			open = true;
			loading = true;
			try {
				const data = await import('$lib/api.js').then((m) => m.getNotifications(5, 0));
				items = data.items;
				notifications.unread = data.unread;
			} catch {
				// ignore
			} finally {
				loading = false;
			}
		} else {
			open = false;
		}
	}

	async function handleItem(item) {
		if (!item.read_at) {
			await notifications.markRead(item.id);
			items = items.map((n) =>
				n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n
			);
		}
		if (item.product_id) {
			open = false;
			goto(`/prices/${item.product_id}`);
		}
	}

	async function handleMarkAll(e) {
		e.stopPropagation();
		await notifications.markAllRead();
		items = items.map((n) => ({ ...n, read_at: new Date().toISOString() }));
	}

	function close() {
		open = false;
	}
</script>

<svelte:window onclick={close} />

<div class="relative">
	<button
		onclick={toggle}
		class="relative grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
		aria-label="Notifications"
	>
		<Bell class="size-4.5" />
		{#if notifications.unread > 0}
			<span class="absolute top-1 right-1 size-2 rounded-full bg-red-500 ring-2 ring-background"
			></span>
		{/if}
	</button>

	{#if open}
		<div
			transition:fly={{ y: -6, duration: 150 }}
			onclick={(e) => e.stopPropagation()}
			class="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border bg-popover shadow-lg sm:w-96"
		>
			<!-- header -->
			<div class="flex items-center justify-between border-b px-4 py-3">
				<span class="text-sm font-semibold">Notifications</span>
				{#if notifications.unread > 0}
					<button
						onclick={handleMarkAll}
						class="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
					>
						<CheckCheck class="size-3.5" />
						Mark all read
					</button>
				{/if}
			</div>

			<!-- list -->
			<div class="max-h-80 divide-y overflow-y-auto">
				{#if loading}
					{#each Array(3) as _}
						<div class="flex gap-3 px-4 py-3">
							<div class="size-8 shrink-0 animate-pulse rounded-full bg-muted"></div>
							<div class="flex-1 space-y-1.5">
								<div class="h-3.5 w-3/4 animate-pulse rounded bg-muted"></div>
								<div class="h-3 w-1/2 animate-pulse rounded bg-muted"></div>
							</div>
						</div>
					{/each}
				{:else if items.length === 0}
					<div class="flex flex-col items-center gap-2 py-10 text-center">
						<Bell class="size-8 text-muted-foreground/30" />
						<p class="text-sm text-muted-foreground">No notifications yet</p>
					</div>
				{:else}
					{#each items as item}
						{@const k = KIND[item.kind] ?? KIND.price_drop}
						{@const Icon = k.icon}
						{@const unread = !item.read_at}
						<button
							onclick={() => handleItem(item)}
							class="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60 {unread
								? 'bg-primary/5'
								: ''}"
						>
							<!-- kind icon -->
							<div
								class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full {k.bg}"
							>
								<Icon class="size-4 {k.color}" />
							</div>

							<div class="min-w-0 flex-1">
								<div class="flex items-start justify-between gap-2">
									<p class="truncate text-sm leading-snug font-medium">{item.title}</p>
									{#if unread}
										<span class="mt-1 size-2 shrink-0 rounded-full bg-primary"></span>
									{/if}
								</div>
								<p class="mt-0.5 truncate text-xs text-muted-foreground">{item.message}</p>
								<p class="mt-1 text-xs text-muted-foreground/60">{reltime(item.sent_at)}</p>
							</div>
						</button>
					{/each}
				{/if}
			</div>

			<!-- footer -->
			<div class="border-t px-4 py-2.5">
				<a
					href="/notifications"
					onclick={() => (open = false)}
					class="flex items-center justify-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
				>
					View all notifications
					<ArrowRight class="size-3.5" />
				</a>
			</div>
		</div>
	{/if}
</div>
