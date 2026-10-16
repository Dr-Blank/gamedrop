<script>
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { Activity, CheckCheck, Clock, Heart } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import InfiniteScroll from '$lib/components/InfiniteScroll.svelte';
	import ProductImage from '$lib/components/ProductImage.svelte';
	import TimelineChart from '$lib/components/TimelineChart.svelte';
	import { getTimelineEvents, getTimelineSeen, markTimelineSeen } from '$lib/api.js';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { inrDelta, inrExact } from '$lib/priceFormat.svelte.js';
	import { fmtDateParts } from '$lib/dateFormat.svelte.js';
	import { KINDS, groupEvents, localDay, pctMove, stampOf } from '$lib/timeline.js';
	import { toast } from '$lib/toast.svelte.js';

	const STORAGE_KEY = 'gd-timeline-filters';
	const PAGE = 100;
	const CHART_DAYS = 30;

	const DAY = 86_400_000;
	const WINDOWS = [
		{ key: '1d', label: '24h', ms: DAY },
		{ key: '3d', label: '3 days', ms: 3 * DAY },
		{ key: '1w', label: 'Week', ms: 7 * DAY },
		{ key: '1mo', label: 'Month', ms: 30 * DAY },
		{ key: 'all', label: 'All', ms: null }
	];

	const KIND_LABELS = {
		drop: 'Drops',
		rise: 'Rises',
		restock: 'Restocks',
		oos: 'Sold out',
		listed: 'New'
	};

	const defaults = () => ({
		window: '1w',
		/** @type {string[]} empty = every shop */
		stores: [],
		/** @type {string[]} empty = every kind */
		kinds: [],
		minPct: /** @type {number|null} */ (null),
		watchlist: false
	});

	function restore() {
		if (!browser) return defaults();
		try {
			return { ...defaults(), ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') };
		} catch {
			return defaults();
		}
	}

	let filters = $state(restore());
	let events = $state(/** @type {Array<any>} */ ([]));
	let games = $state(/** @type {Record<string, any>} */ ({}));
	let cursor = $state(/** @type {string|null} */ (null));
	let loading = $state(false);
	let loaded = $state(false);
	let request = 0;
	// Pinned per fresh load so later pages page through the same window.
	let loadedAt = $state(Date.now());
	let seenAt = $state(/** @type {string|null} */ (null));

	const stores = $derived([...storeColors.names.keys()].sort());
	const seenStamp = $derived(seenAt ? stampOf(seenAt) : null);
	const days = $derived(groupEvents(events, seenStamp));
	const unseen = $derived(
		seenStamp == null ? events.length : events.filter((e) => stampOf(e.at) > seenStamp).length
	);
	const caughtUpKey = $derived(days.flatMap((d) => d.groups).find((g) => g.seen)?.key ?? null);
	// The seen line is global, so marking from a narrowed view would skip what it hides.
	const narrowed = $derived(
		!!(filters.stores.length || filters.kinds.length || filters.minPct || filters.watchlist)
	);

	function params(before = /** @type {string|null} */ (null)) {
		const span = WINDOWS.find((w) => w.key === filters.window)?.ms;
		return {
			since: span ? new Date(loadedAt - span).toISOString() : null,
			stores: filters.stores.join(','),
			kinds: filters.kinds.join(','),
			min_pct: filters.minPct || null,
			watchlist: filters.watchlist,
			before,
			limit: PAGE
		};
	}

	async function load(more = false) {
		const mine = ++request;
		loading = true;
		if (!more) loadedAt = Date.now();
		try {
			const body = await getTimelineEvents(params(more ? cursor : null));
			if (mine !== request) return;
			events = more ? [...events, ...body.events] : body.events;
			games = more ? { ...games, ...body.games } : body.games;
			cursor = body.next_cursor;
		} catch (e) {
			if (mine !== request) return;
			toast.error(`Could not load the timeline: ${e}`);
			if (!more) {
				events = [];
				games = {};
				cursor = null;
			}
		} finally {
			if (mine === request) {
				loading = false;
				loaded = true;
			}
		}
	}

	function update(/** @type {Partial<ReturnType<typeof defaults>>} */ patch) {
		filters = { ...filters, ...patch };
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
		} catch {
			// Remembering filters is a convenience; the page works without it.
		}
		load();
	}

	/** @param {string[]} list @param {string} item */
	const toggled = (list, item) =>
		list.includes(item) ? list.filter((x) => x !== item) : [...list, item];

	onMount(() => {
		load();
		getTimelineSeen()
			.then((body) => (seenAt = body.seen_at))
			.catch(() => {});
	});

	/** Up to the newest move loaded, not "now": a change landing meanwhile stays new. */
	async function markCaughtUp() {
		try {
			seenAt = (await markTimelineSeen(events[0]?.at ?? null)).seen_at;
		} catch (e) {
			toast.error(`Could not mark caught up: ${e}`);
		}
	}

	/** Only the chosen shops are charted; with none chosen, every shop is. */
	function chartSeries(/** @type {any} */ game) {
		const all = game?.series ?? [];
		return filters.stores.length ? all.filter((s) => filters.stores.includes(s.store_id)) : all;
	}

	function chartFrom(/** @type {any} */ group) {
		const oldest = Math.min(...group.events.map((e) => stampOf(e.since ?? e.at)));
		return oldest - CHART_DAYS * 86_400_000;
	}

	function dayLabel(/** @type {string} */ day) {
		const today = localDay(new Date().toISOString());
		const yesterday = localDay(new Date(Date.now() - 86_400_000).toISOString());
		if (day === today) return 'Today';
		if (day === yesterday) return 'Yesterday';
		return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	const time = (/** @type {string} */ at) =>
		fmtDateParts(at, { hour: '2-digit', minute: '2-digit' });

	const pctLabel = (/** @type {any} */ e) => {
		const p = pctMove(e);
		return p == null ? '' : `${p > 0 ? '+' : ''}${p.toFixed(1)}%`;
	};
</script>

<div class="space-y-5">
	<div class="flex items-center justify-between gap-3">
		<div>
			<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<Activity class="size-6 text-primary" />
				Timeline
			</h1>
			<p class="mt-1 text-sm text-muted-foreground">
				Every price and stock move across shops, newest first.
			</p>
		</div>
		<Button
			size="sm"
			variant={unseen ? 'default' : 'outline'}
			disabled={!unseen || narrowed}
			title={narrowed ? 'Clear the shop, kind and size filters to mark caught up' : undefined}
			onclick={markCaughtUp}
		>
			<CheckCheck class="size-4" />
			{unseen ? `Mark ${unseen}${cursor ? '+' : ''} as seen` : 'Caught up'}
		</Button>
	</div>

	<div class="flex flex-col gap-3 rounded-lg border p-3">
		<div class="flex flex-wrap items-center gap-1.5">
			<Clock class="mr-1 size-4 text-muted-foreground" />
			{#each WINDOWS as w (w.key)}
				<Button
					size="sm"
					variant={filters.window === w.key ? 'default' : 'outline'}
					aria-pressed={filters.window === w.key}
					onclick={() => update({ window: w.key })}
				>
					{w.label}
				</Button>
			{/each}
		</div>

		<div class="flex flex-wrap items-center gap-1.5">
			{#each KINDS as kind (kind)}
				{@const on = filters.kinds.length === 0 || filters.kinds.includes(kind)}
				<Button
					size="sm"
					variant={on ? 'secondary' : 'ghost'}
					aria-pressed={filters.kinds.includes(kind)}
					onclick={() => update({ kinds: toggled(filters.kinds, kind) })}
				>
					{KIND_LABELS[kind]}
				</Button>
			{/each}
			<label class="ml-auto flex items-center gap-1.5 text-sm text-muted-foreground">
				Price moves ≥
				<input
					type="number"
					min="0"
					step="1"
					value={filters.minPct ?? ''}
					onchange={(e) => {
						const v = parseFloat(/** @type {HTMLInputElement} */ (e.currentTarget).value);
						update({ minPct: Number.isFinite(v) && v > 0 ? v : null });
					}}
					class="h-8 w-16 rounded-md border bg-background px-2 text-foreground tabular-nums"
					aria-label="Smallest price move to show, in percent"
				/>
				%
			</label>
			<Button
				size="sm"
				variant={filters.watchlist ? 'secondary' : 'ghost'}
				aria-pressed={filters.watchlist}
				onclick={() => update({ watchlist: !filters.watchlist })}
			>
				<Heart class="size-4" />
				Watchlist
			</Button>
		</div>

		{#if stores.length > 1}
			<div class="flex flex-wrap items-center gap-2">
				{#each stores as id (id)}
					{@const on = filters.stores.includes(id)}
					<button
						onclick={() => update({ stores: toggled(filters.stores, id) })}
						aria-pressed={on}
						class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-muted/50 {on ||
						filters.stores.length === 0
							? 'text-foreground'
							: 'text-muted-foreground/60'}"
					>
						<span
							class="size-2 rounded-full"
							style:background-color={on ? storeColors.of(id) : 'transparent'}
							style:box-shadow="inset 0 0 0 1.5px {storeColors.of(id)}"
						></span>
						{storeColors.name(id)}
					</button>
				{/each}
				{#if filters.stores.length}
					<button
						class="text-xs text-primary hover:underline"
						onclick={() => update({ stores: [] })}
					>
						All shops
					</button>
				{/if}
			</div>
		{/if}
	</div>

	{#if loaded && !events.length}
		<div class="rounded-lg border border-dashed p-10 text-center">
			<p class="font-medium">Nothing moved</p>
			<p class="mt-1 text-sm text-muted-foreground">No changes match these filters.</p>
		</div>
	{/if}

	{#each days as day (day.day)}
		<section class="space-y-2">
			<h2 class="text-sm font-semibold text-muted-foreground">{dayLabel(day.day)}</h2>
			{#each day.groups as group (group.key)}
				{@const game = games[group.game_id]}
				{@const series = chartSeries(game)}
				{#if group.key === caughtUpKey}
					<div class="flex items-center gap-3 py-2 text-xs font-medium text-primary">
						<span class="h-px flex-1 bg-primary/40"></span>
						<CheckCheck class="size-4" />
						Caught up — seen {fmtDateParts(seenAt, {
							day: 'numeric',
							month: 'short',
							hour: '2-digit',
							minute: '2-digit'
						})}
						<span class="h-px flex-1 bg-primary/40"></span>
					</div>
				{/if}
				<article class="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row">
					<div class="flex min-w-0 flex-1 gap-3">
						<a href="/games/{group.game_id}" class="shrink-0">
							<ProductImage
								src={game?.image_url ?? ''}
								alt={game?.title ?? ''}
								class="size-14 rounded-md"
							/>
						</a>
						<div class="min-w-0 flex-1">
							<a href="/games/{group.game_id}" class="font-medium hover:underline">
								{game?.title ?? `Game ${group.game_id}`}
							</a>
							<ul class="mt-1 space-y-0.5">
								{#each group.events as e (e.snapshot_id)}
									{@const color = storeColors.of(e.store_id)}
									<li class="flex flex-wrap items-baseline gap-x-2 text-sm">
										<span class="inline-flex items-center gap-1 text-xs" style:color>
											<span class="size-2 rounded-full" style:background-color={color}></span>
											{storeColors.name(e.store_id)}
										</span>
										{#if e.kind === 'drop' || e.kind === 'rise'}
											{@const good = e.kind === 'drop'}
											<span class="text-muted-foreground tabular-nums line-through">
												{inrExact(e.prev_price)}
											</span>
											<span
												class="font-semibold tabular-nums {good
													? 'text-green-600 dark:text-green-400'
													: 'text-rose-500'}"
											>
												{inrExact(e.price)}
											</span>
											<span
												class="text-xs tabular-nums {good
													? 'text-green-600 dark:text-green-400'
													: 'text-rose-500'}"
											>
												{inrDelta(e.price - e.prev_price)} · {pctLabel(e)}
											</span>
										{:else if e.kind === 'flaps'}
											<span>In and out of stock {e.count}×</span>
											<span class="tabular-nums">{inrExact(e.price)}</span>
										{:else}
											<span>
												{e.kind === 'listed'
													? 'New listing'
													: e.kind === 'oos'
														? 'Sold out'
														: 'Back in stock'}
											</span>
											<span class="font-semibold tabular-nums">{inrExact(e.price)}</span>
										{/if}
										{#if e.variant_title}
											<span class="text-xs text-muted-foreground">{e.variant_title}</span>
										{/if}
										<span class="text-xs text-muted-foreground">{time(e.at)}</span>
									</li>
								{/each}
							</ul>
						</div>
					</div>
					{#if series.length}
						<div class="shrink-0 sm:w-72">
							<TimelineChart
								{series}
								focus={new Set(group.events.map((e) => e.store_id))}
								marks={group.events.filter((e) => e.kind === 'drop' || e.kind === 'rise')}
								from={chartFrom(group)}
								to={loadedAt}
							/>
						</div>
					{/if}
				</article>
			{/each}
		</section>
	{/each}

	<InfiniteScroll hasMore={!!cursor} {loading} onload={() => load(true)} />
</div>
