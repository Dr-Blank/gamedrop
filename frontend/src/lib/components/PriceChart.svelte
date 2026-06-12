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
		history = /** @type {Array<{price:number, recorded_at:string, available:boolean}>} */ ([])
	} = $props();

	const ranges = [
		{ key: '30', label: '30D', days: 30 },
		{ key: '90', label: '90D', days: 90 },
		{ key: 'all', label: 'All', days: Infinity }
	];
	let rangeKey = $state('90');

	// chronological (oldest → newest)
	const chrono = $derived(history.slice().reverse());

	const windowed = $derived.by(() => {
		const r = ranges.find((x) => x.key === rangeKey);
		if (!r || r.days === Infinity) return chrono;
		const cutoff = Date.now() - r.days * 86400000;
		const f = chrono.filter((h) => new Date(h.recorded_at).getTime() >= cutoff);
		return f.length >= 2 ? f : chrono;
	});

	const stats = $derived.by(() => {
		const ps = windowed.map((h) => h.price);
		if (!ps.length) return null;
		const min = Math.min(...ps);
		const max = Math.max(...ps);
		const cur = ps[ps.length - 1];
		const first = ps[0];
		const avg = ps.reduce((a, b) => a + b, 0) / ps.length;
		const change = cur - first;
		const changePct = first ? (change / first) * 100 : 0;
		return { min, max, cur, avg, change, changePct, atLow: cur <= min + 0.01 };
	});

	const fmt = (/** @type {number} */ n) =>
		`₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

	let canvas = $state(/** @type {HTMLCanvasElement | null} */ (null));
	let chart;

	function build() {
		if (!canvas || windowed.length < 2) {
			chart?.destroy();
			chart = null;
			return;
		}
		const css = getComputedStyle(document.documentElement);
		const muted = css.getPropertyValue('--muted-foreground').trim() || '#888';
		const border = theme.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';
		const accent = '#10b981';

		const labels = windowed.map((h) =>
			new Date(h.recorded_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
		);
		const data = windowed.map((h) => h.price);

		const ctx = canvas.getContext('2d');
		const grad = ctx.createLinearGradient(0, 0, 0, 240);
		grad.addColorStop(0, 'rgba(16,185,129,0.25)');
		grad.addColorStop(1, 'rgba(16,185,129,0)');

		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						data,
						borderColor: accent,
						backgroundColor: grad,
						fill: true,
						tension: 0.32,
						borderWidth: 2,
						pointRadius: windowed.length > 40 ? 0 : 3,
						pointHoverRadius: 5,
						pointBackgroundColor: accent
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: 'index', intersect: false },
				plugins: {
					legend: { display: false },
					tooltip: {
						callbacks: { label: (c) => fmt(c.parsed.y) },
						padding: 10,
						displayColors: false
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
		windowed;
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
					<div class="text-xs text-muted-foreground">Current</div>
					<div class="text-lg font-bold tabular-nums">{fmt(stats.cur)}</div>
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
