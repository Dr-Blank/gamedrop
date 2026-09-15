<script>
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Tooltip
	} from 'chart.js';
	import { theme } from '$lib/theme.svelte.js';
	import {
		alignSeries,
		clipToWindow,
		dayKey,
		formatDay,
		segmentInStock
	} from '$lib/priceSeries.js';
	import { storeColors, DEFAULT_PALETTE, tint } from '$lib/storeColors.svelte.js';
	import { inr, inrDelta, priceFormat } from '$lib/priceFormat.svelte.js';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Tooltip
	);

	let {
		series = /** @type {Array<{label?:string, store_id?:string, history:Array<any>}>} */ ([])
	} = $props();

	const sources = $derived(series ?? []);
	const multi = $derived(sources.length > 1);

	const ranges = [
		{ key: '30', label: '30D', days: 30 },
		{ key: '90', label: '90D', days: 90 },
		{ key: 'all', label: 'All', days: Infinity }
	];
	let rangeKey = $state('90');

	const view = $derived.by(() => {
		const r = ranges.find((x) => x.key === rangeKey);
		const to = dayKey(Date.now());
		if (!r || r.days === Infinity) {
			const days = sources
				.flatMap((s) => (s.history ?? []).map((h) => dayKey(h.recorded_at)))
				.sort();
			return { series: sources, bounds: days.length ? { from: days[0], to } : null };
		}
		const cutoff = Date.now() - r.days * 86400000;
		return { series: clipToWindow(sources, cutoff), bounds: { from: dayKey(cutoff), to } };
	});

	const windowed = $derived(view.series);
	const aligned = $derived(alignSeries(view.series, view.bounds));

	const stats = $derived.by(() => {
		const all = windowed.flatMap((s) => (s.history ?? []).map((h) => h.price));
		if (!all.length) return null;
		const min = Math.min(...all);
		const max = Math.max(...all);
		const lasts = windowed
			.map((s) => {
				const h = s.history ?? [];
				return h.length ? { label: s.label ?? s.store_id, price: h[h.length - 1].price } : null;
			})
			.filter(Boolean);
		const best = lasts.length
			? lasts.reduce((a, b) => (b.price < a.price ? b : a))
			: { label: '', price: null };
		const firsts = windowed.flatMap((s) => (s.history?.length ? [s.history[0].price] : []));
		const first = firsts.length ? Math.min(...firsts) : null;
		const change = first != null && best.price != null ? best.price - first : 0;
		return {
			min,
			max,
			best,
			change,
			changePct: first ? (change / first) * 100 : 0,
			atLow: best.price != null && best.price <= min + 0.01
		};
	});

	let canvas = $state(/** @type {HTMLCanvasElement | null} */ (null));
	let chart;

	function build() {
		const points = aligned.datasets.reduce((n, d) => n + d.data.filter((v) => v != null).length, 0);
		if (!canvas || !aligned.labels.length || !points) {
			chart?.destroy();
			chart = null;
			return;
		}
		const css = getComputedStyle(document.documentElement);
		const muted = css.getPropertyValue('--muted-foreground').trim() || '#888';
		const border = theme.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';

		const ctx = canvas.getContext('2d');
		const soloColor = aligned.datasets[0]?.storeId
			? storeColors.of(aligned.datasets[0].storeId)
			: DEFAULT_PALETTE[0];
		const grad = ctx.createLinearGradient(0, 0, 0, 240);
		grad.addColorStop(0, tint(soloColor, 0.25));
		grad.addColorStop(1, tint(soloColor, 0));

		const dense = aligned.labels.length > 60;

		const datasets = aligned.datasets.map((d, i) => {
			const color = d.storeId
				? storeColors.of(d.storeId)
				: DEFAULT_PALETTE[i % DEFAULT_PALETTE.length];
			const scraped = (/** @type {any} */ ctx) => d.real[ctx.dataIndex];
			const sold = (/** @type {any} */ ctx) => d.available[ctx.dataIndex] !== false;
			const debut = (/** @type {any} */ ctx) => d.entry[ctx.dataIndex];
			return {
				label: d.label,
				data: d.data,
				borderColor: color,
				backgroundColor: multi ? color : grad,
				fill: !multi,
				spanGaps: true,
				tension: 0.32,
				borderWidth: 2,
				// Only scraped days get a marker — a forward-filled price is the
				// same reading, not a second one.
				pointRadius: (ctx) =>
					scraped(ctx) ? (debut(ctx) ? 5 : sold(ctx) ? (dense ? 2.5 : 3.5) : 4) : 0,
				pointHoverRadius: (ctx) => (scraped(ctx) ? 6 : 0),
				// A diamond is the listing appearing for the first time, not a price move.
				pointStyle: (ctx) => (debut(ctx) ? 'rectRot' : sold(ctx) ? 'circle' : 'crossRot'),
				pointBackgroundColor: (ctx) => (sold(ctx) ? color : 'transparent'),
				pointBorderColor: color,
				pointBorderWidth: 2,
				segment: {
					// A stretch with nothing to buy is drawn broken and faded.
					borderDash: (ctx) => (segmentInStock(d.available, ctx.p0DataIndex) ? undefined : [5, 4]),
					borderColor: (ctx) =>
						segmentInStock(d.available, ctx.p0DataIndex) ? undefined : tint(color, 0.35)
				}
			};
		});

		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'line',
			data: { labels: aligned.labels.map(formatDay), datasets },
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: 'index', intersect: false },
				plugins: {
					legend: { display: false },
					tooltip: {
						callbacks: {
							label: (c) => {
								const d = aligned.datasets[c.datasetIndex];
								const i = c.dataIndex;
								const head = multi ? `${c.dataset.label}: ${inr(c.parsed.y)}` : inr(c.parsed.y);
								const notes = [];
								if (d?.carried[i]) notes.push('carried in from before this range');
								else if (d?.entry[i]) notes.push('first seen');
								else if (!d?.real[i]) notes.push('last seen');
								if (d?.available[i] === false) notes.push('out of stock');
								if (d?.delta[i]) notes.push(`${inrDelta(d.delta[i])} vs previous`);
								return notes.length ? `${head} · ${notes.join(' · ')}` : head;
							}
						},
						padding: 10,
						displayColors: multi
					}
				},
				scales: {
					x: {
						grid: { display: false },
						ticks: { color: muted, maxTicksLimit: 7, font: { size: 11 } }
					},
					y: {
						grid: { color: border },
						border: { display: false },
						ticks: {
							color: muted,
							callback: (v) => inr(v),
							font: { size: 11 },
							maxTicksLimit: 6
						}
					}
				}
			}
		});
	}

	$effect(() => {
		// re-run on data/range/theme/palette change
		aligned;
		theme.isDark;
		storeColors.saved;
		priceFormat.mode;
		build();
		return () => {
			chart?.destroy();
			chart = null;
		};
	});
</script>

<div class="space-y-4">
	{#if stats}
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
				<div>
					<div class="text-xs text-muted-foreground">{multi ? 'Best now' : 'Current'}</div>
					<div class="text-lg font-bold tabular-nums">
						{stats.best.price != null ? inr(stats.best.price) : '—'}
					</div>
					{#if multi && stats.best.label}
						<div class="text-[0.7rem] text-muted-foreground">{stats.best.label}</div>
					{/if}
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Lowest</div>
					<div class="text-lg font-bold text-green-600 tabular-nums dark:text-green-400">
						{inr(stats.min)}
					</div>
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Highest</div>
					<div class="text-lg font-bold tabular-nums">{inr(stats.max)}</div>
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Change</div>
					<div
						title="{stats.changePct > 0 ? '+' : ''}{stats.changePct.toFixed(1)}%"
						class="text-lg font-bold tabular-nums {stats.change < 0
							? 'text-green-600 dark:text-green-400'
							: stats.change > 0
								? 'text-rose-500'
								: ''}"
					>
						{inrDelta(stats.change)}
					</div>
				</div>
			</div>

			<div class="inline-flex rounded-lg border bg-muted/40 p-0.5">
				{#each ranges as r}
					<button
						onclick={() => (rangeKey = r.key)}
						class="rounded-md px-3 py-1 text-xs font-medium transition-colors {rangeKey === r.key
							? 'bg-background text-foreground shadow-sm'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						{r.label}
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<div class="h-60">
		<canvas bind:this={canvas}></canvas>
	</div>
</div>
