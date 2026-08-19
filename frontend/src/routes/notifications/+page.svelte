<script>
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import {
		Bell,
		TrendingDown,
		TrendingUp,
		Package,
		PackageX,
		Crosshair,
		CheckCheck,
		ExternalLink,
		RefreshCw,
		History
	} from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import {
		getNotifications,
		markAllNotificationsRead,
		markNotificationRead,
		backfillNotifications
	} from '$lib/api.js';
	import { notifications as notifStore } from '$lib/notifications.svelte.js';
	import { Button } from '$lib/components/ui/button';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import InfiniteScroll from '$lib/components/InfiniteScroll.svelte';
	import { shortcuts, NOTIFICATION_SHORTCUTS } from '$lib/shortcuts.svelte.js';
	import { fmtRelative, fmtDateParts } from '$lib/dateFormat.svelte.js';

	const PAGE_SIZE = 20;

	/** @type {any[]} */
	let items = $state([]);
	let unread = $state(0);
	let loading = $state(true);
	let loadingMore = $state(false);
	let hasMore = $state(false);
	let offset = $state(0);
	let error = $state('');
	let backfilling = $state(false);
	let backfillDone = $state(/** @type {number|null} */ null);

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

	const reltime = fmtRelative;

	function dayLabel(ts) {
		const d = new Date(ts + 'Z');
		const now = new Date();
		const diff = now.setHours(0, 0, 0, 0) - d.setHours(0, 0, 0, 0);
		if (diff <= 0) return 'Today';
		if (diff <= 86_400_000) return 'Yesterday';
		const days = Math.floor(diff / 86_400_000);
		if (days < 7) return `${days} days ago`;
		return fmtDateParts(ts, {
			weekday: 'long',
			day: 'numeric',
			month: 'short'
		});
	}

	/** Group items by calendar day */
	let grouped = $derived(() => {
		/** @type {Map<string, any[]>} */
		const map = new Map();
		for (const item of items) {
			const label = dayLabel(item.sent_at);
			if (!map.has(label)) map.set(label, []);
			map.get(label).push(item);
		}
		return [...map.entries()];
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const data = await getNotifications(PAGE_SIZE, 0);
			items = data.items;
			unread = data.unread;
			offset = PAGE_SIZE;
			hasMore = data.items.length === PAGE_SIZE;
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function loadMore() {
		loadingMore = true;
		try {
			const data = await getNotifications(PAGE_SIZE, offset);
			items = [...items, ...data.items];
			offset += PAGE_SIZE;
			hasMore = data.items.length === PAGE_SIZE;
		} catch {
			// ignore
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => shortcuts.register(NOTIFICATION_SHORTCUTS, { u: markAllRead }));

	async function markAllRead() {
		await markAllNotificationsRead();
		items = items.map((n) => ({ ...n, read_at: new Date().toISOString() }));
		unread = 0;
		notifStore.unread = 0;
	}

	async function markRead(item) {
		if (!item.read_at) {
			await markNotificationRead(item.id);
			items = items.map((n) =>
				n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n
			);
			unread = Math.max(0, unread - 1);
			notifStore.unread = Math.max(0, notifStore.unread - 1);
		}
		if (item.game_id) {
			goto(`/games/${item.game_id}`);
		} else if (item.product_id) {
			goto(`/prices/${item.product_id}`);
		}
	}

	async function runBackfill() {
		backfilling = true;
		backfillDone = null;
		try {
			const result = await backfillNotifications();
			backfillDone = result.inserted;
			if (result.inserted > 0) await load();
		} catch {
			backfillDone = -1;
		} finally {
			backfilling = false;
		}
	}

	onMount(load);
</script>

<div class="space-y-6">
	<!-- Page header -->
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<Bell class="size-6 text-primary" />
				Notifications
			</h1>
			<p class="mt-1 text-sm text-muted-foreground">
				{#if loading}
					Loading…
				{:else}
					{items.length} notification{items.length === 1 ? '' : 's'}
					{#if unread > 0}
						<span
							class="ml-1 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground"
							>{unread} unread</span
						>
					{/if}
				{/if}
			</p>
		</div>

		<div class="flex items-center gap-2">
			<!-- Backfill historical -->
			<Button
				variant="outline"
				size="sm"
				onclick={runBackfill}
				disabled={backfilling}
				class="gap-2"
			>
				{#if backfilling}
					<RefreshCw class="size-3.5 animate-spin" />
					Backfilling…
				{:else}
					<History class="size-3.5" />
					Load history
				{/if}
			</Button>

			{#if unread > 0}
				<Button variant="outline" size="sm" onclick={markAllRead} class="gap-2">
					<CheckCheck class="size-3.5" />
					Mark all read
				</Button>
			{/if}
		</div>
	</div>

	<!-- Backfill result -->
	{#if backfillDone !== null}
		<div
			transition:fly={{ y: -8, duration: 200 }}
			class="rounded-lg border {backfillDone < 0
				? 'border-destructive/30 bg-destructive/5 text-destructive'
				: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800/30 dark:bg-emerald-900/20 dark:text-emerald-300'} px-4 py-3 text-sm"
		>
			{#if backfillDone < 0}
				Backfill failed — check server logs.
			{:else if backfillDone === 0}
				History is already up to date — no new notifications added.
			{:else}
				Added {backfillDone} historical notification{backfillDone === 1 ? '' : 's'}.
			{/if}
		</div>
	{/if}

	<!-- Loading skeletons -->
	{#if loading}
		<div class="space-y-1">
			{#each Array(6) as _}
				<div class="flex items-start gap-3 rounded-xl border px-4 py-3">
					<Skeleton class="mt-0.5 size-9 shrink-0 rounded-full" />
					<div class="flex-1 space-y-2">
						<Skeleton class="h-4 w-2/3" />
						<Skeleton class="h-3 w-1/2" />
					</div>
					<Skeleton class="h-3 w-16 shrink-0" />
				</div>
			{/each}
		</div>
	{:else if error}
		<p class="text-sm text-destructive">Error: {error}</p>
	{:else if items.length === 0}
		<div
			class="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-20 text-center"
		>
			<Bell class="size-12 text-muted-foreground/30" />
			<div>
				<p class="font-medium">No notifications yet</p>
				<p class="mt-1 text-sm text-muted-foreground">
					Add games to your watchlist to start receiving alerts.
				</p>
			</div>
			<div class="flex gap-2">
				<Button variant="outline" href="/watchlist" size="sm">Go to Watchlist</Button>
				<Button variant="outline" onclick={runBackfill} size="sm" disabled={backfilling}>
					<History class="size-3.5" />
					Load history
				</Button>
			</div>
		</div>
	{:else}
		<!-- Grouped list -->
		<div class="space-y-6">
			{#each grouped() as [day, dayItems]}
				<div>
					<!-- Day label -->
					<div class="mb-2 flex items-center gap-3">
						<span class="text-xs font-semibold tracking-wider text-muted-foreground uppercase"
							>{day}</span
						>
						<div class="h-px flex-1 bg-border"></div>
					</div>

					<div class="overflow-hidden rounded-xl border">
						{#each dayItems as item, i}
							{@const k = KIND[item.kind] ?? KIND.price_drop}
							{@const Icon = k.icon}
							{@const unreadItem = !item.read_at}
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								class="group flex items-start gap-3 px-4 py-3.5 transition-colors
									{unreadItem ? 'bg-primary/[0.03]' : 'bg-background'}
									{i > 0 ? 'border-t' : ''}
									hover:bg-muted/40"
								role="button"
								tabindex="0"
								onclick={() => markRead(item)}
								onkeydown={(e) => e.key === 'Enter' && markRead(item)}
							>
								<!-- Kind icon -->
								<div
									class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full {k.bg}"
								>
									<Icon class="size-4.5 {k.color}" />
								</div>

								<!-- Content -->
								<div class="min-w-0 flex-1">
									<div class="flex items-start gap-2">
										<div class="min-w-0 flex-1">
											<p
												class="truncate text-sm leading-snug font-medium {unreadItem
													? ''
													: 'text-muted-foreground'}"
											>
												{item.title}
											</p>
											<p class="mt-0.5 text-xs text-muted-foreground">
												{item.message}
											</p>
										</div>
										<!-- Unread dot -->
										{#if unreadItem}
											<span class="mt-1.5 size-2 shrink-0 rounded-full bg-primary"></span>
										{/if}
									</div>
								</div>

								<!-- Right side: time + action -->
								<div class="flex shrink-0 flex-col items-end gap-2">
									<span class="text-xs text-muted-foreground/60">{reltime(item.sent_at)}</span>
									{#if item.product_url}
										<a
											href={item.product_url}
											target="_blank"
											rel="noopener"
											onclick={(e) => e.stopPropagation()}
											class="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-muted hover:text-foreground"
										>
											Store <ExternalLink class="size-3" />
										</a>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>

		<InfiniteScroll {hasMore} loading={loadingMore} onload={loadMore} />
	{/if}
</div>
