<script>
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Legend,
		Tooltip
	} from 'chart.js';
	import { theme } from '$lib/theme.svelte.js';
	import { alignSeries, formatDay } from '$lib/priceSeries.js';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Legend,
		Tooltip
	);

	let {
		history = /** @type {Array<{price:number, recorded_at:string, available:boolean}>} */ ([]),
		series = /** @type {Array<{label?:string, store_id?:string, history:Array<any>}>|null} */ (null)
	} = $props();

	// One store or many: everything downstream works on a list of series.
	const sources = $derived(
		series?.length ? series : [{ label: 'Price', history: history.slice().reverse() }]
	);
	const multi = $derived((series?.length ?? 0) > 1);

	const ranges = [
		{ key: '30', label: '30D', days: 30 },
		{ key: '90', label: '90D', days: 90 },
		{ key: 'all', label: 'All', days: Infinity }
	];
	let rangeKey = $state('90');

	const windowed = $derived.by(() => {
		const r = ranges.find((x) => x.key === rangeKey);
		if (!r || r.days === Infinity) return sources;
		const cutoff = Date.now() - r.days * 86400000;
		const clipped = sources.map((s) => ({
			...s,
			history: (s.history ?? []).filter((h) => new Date(h.recorded_at).getTime() >= cutoff)
		}));
		const points = clipped.reduce((n, s) => n + s.history.length, 0);
		return points >= 2 ? clipped : sources;
	});

	const aligned = $derived(alignSeries(windowed));

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

	const fmt = (/** @type {number} */ n) =>
		`₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

	const PALETTE = ['#10b981', '#6366f1', '#f59e0b', '#ec4899', '#06b6d4', '#a855f7'];

	let canvas = $state(/** @type {HTMLCanvasElement | null} */ (null));
	let chart;

	function build() {
		const points = aligned.datasets.reduce((n, d) => n + d.data.filter((v) => v != null).length, 0);
		if (!canvas || aligned.labels.length < 2 || points < 2) {
			chart?.destroy();
			chart = null;
			return;
		}
		const css = getComputedStyle(document.documentElement);
		const muted = css.getPropertyValue('--muted-foreground').trim() || '#888';
		const border = theme.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';

		const ctx = canvas.getContext('2d');
		const grad = ctx.createLinearGradient(0, 0, 0, 240);
		grad.addColorStop(0, 'rgba(16,185,129,0.25)');
		grad.addColorStop(1, 'rgba(16,185,129,0)');

		const datasets = aligned.datasets.map((d, i) => {
			const color = PALETTE[i % PALETTE.length];
			return {
				label: d.label,
				data: d.data,
				borderColor: color,
				backgroundColor: multi ? color : grad,
				fill: !multi,
				spanGaps: true,
				tension: 0.32,
				borderWidth: 2,
				pointRadius: aligned.labels.length > 40 ? 0 : 3,
				pointHoverRadius: 5,
				pointBackgroundColor: color
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
					legend: {
						display: multi,
						position: 'bottom',
						labels: { color: muted, boxWidth: 10, usePointStyle: true, font: { size: 11 } }
					},
					tooltip: {
						callbacks: {
							label: (c) => (multi ? `${c.dataset.label}: ${fmt(c.parsed.y)}` : fmt(c.parsed.y))
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
						ticks: { color: muted, callback: (v) => `₹${v}`, font: { size: 11 }, maxTicksLimit: 6 }
					}
				}
			}
		});
	}

	$effect(() => {
		// re-run on data/range/theme change
		aligned;
		theme.isDark;
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
						{stats.best.price != null ? fmt(stats.best.price) : '—'}
					</div>
					{#if multi && stats.best.label}
						<div class="text-[0.7rem] text-muted-foreground">{stats.best.label}</div>
					{/if}
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Lowest</div>
					<div class="text-lg font-bold text-green-600 tabular-nums dark:text-green-400">
						{fmt(stats.min)}
					</div>
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Highest</div>
					<div class="text-lg font-bold tabular-nums">{fmt(stats.max)}</div>
				</div>
				<div>
					<div class="text-xs text-muted-foreground">Change</div>
					<div
						class="text-lg font-bold tabular-nums {stats.change < 0
							? 'text-green-600 dark:text-green-400'
							: stats.change > 0
								? 'text-rose-500'
								: ''}"
					>
						{stats.change > 0 ? '+' : ''}{stats.changePct.toFixed(1)}%
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
