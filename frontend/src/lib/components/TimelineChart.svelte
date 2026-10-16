<script>
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { inrExact } from '$lib/priceFormat.svelte.js';
	import { fmtDateParts } from '$lib/dateFormat.svelte.js';
	import { stampOf, valuesAt } from '$lib/timeline.js';

	let {
		series = /** @type {Array<{product_id: number, store_id: string, history: Array<any>}>} */ ([]),
		focus = /** @type {Set<string>} */ (new Set()),
		marks = /** @type {Array<{at: string, price: number, store_id: string}>} */ ([]),
		from = 0,
		to = Date.now(),
		height = 64
	} = $props();

	let width = $state(0);
	let hoverT = $state(/** @type {number|null} */ (null));
	const pad = 4;

	const prices = $derived(
		series.flatMap((s) =>
			s.history.filter((h) => stampOf(h.recorded_at) >= from).map((h) => h.price)
		)
	);
	// A line entering from before the window still sets the scale it enters at.
	const entering = $derived(
		series.flatMap((s) => {
			const before = s.history.filter((h) => stampOf(h.recorded_at) < from);
			return before.length ? [before[before.length - 1].price] : [];
		})
	);
	const yMin = $derived(Math.min(...prices, ...entering));
	const yMax = $derived(Math.max(...prices, ...entering));

	const x = (/** @type {number} */ t) =>
		pad + ((Math.max(t, from) - from) / Math.max(to - from, 1)) * (width - pad * 2);
	const y = (/** @type {number} */ p) =>
		pad + (1 - (p - yMin) / (yMax - yMin || 1)) * (height - pad * 2);

	/** Step segments, split so out-of-stock stretches can be drawn dashed. */
	function segments(/** @type {Array<any>} */ history) {
		const out = [];
		for (let i = 0; i < history.length; i++) {
			const h = history[i];
			const next = history[i + 1];
			const t0 = stampOf(h.recorded_at);
			const t1 = next ? stampOf(next.recorded_at) : Math.max(to, t0);
			if (t1 < from) continue;
			const x0 = x(t0);
			const x1 = x(t1);
			const yy = y(h.price);
			const rise = next ? ` L${x1.toFixed(1)},${y(next.price).toFixed(1)}` : '';
			out.push({
				d: `M${x0.toFixed(1)},${yy.toFixed(1)} L${x1.toFixed(1)},${yy.toFixed(1)}${rise}`,
				available: h.available
			});
		}
		return out;
	}

	const lines = $derived(
		width && prices.length + entering.length
			? series
					.map((s) => ({
						product_id: s.product_id,
						store_id: s.store_id,
						segs: segments(s.history)
					}))
					// Focused shops last, so they draw over the context lines.
					.sort((a, b) => Number(focus.has(a.store_id)) - Number(focus.has(b.store_id)))
			: []
	);

	const readout = $derived(hoverT == null ? [] : valuesAt(series, hoverT));

	function move(/** @type {PointerEvent} */ ev) {
		const rect = /** @type {HTMLElement} */ (ev.currentTarget).getBoundingClientRect();
		const frac = (ev.clientX - rect.left - pad) / Math.max(rect.width - pad * 2, 1);
		hoverT = from + Math.min(Math.max(frac, 0), 1) * (to - from);
	}
</script>

<div
	class="relative w-full"
	style:height="{height}px"
	bind:clientWidth={width}
	onpointermove={move}
	onpointerleave={() => (hoverT = null)}
	role="img"
	aria-label="Price history by shop"
>
	{#if lines.length}
		<svg {width} {height} class="block overflow-visible">
			{#each lines as line (line.product_id)}
				{@const color = storeColors.of(line.store_id)}
				{@const on = focus.size === 0 || focus.has(line.store_id)}
				{#each line.segs as seg}
					<path
						d={seg.d}
						fill="none"
						stroke={color}
						stroke-width={on ? 2 : 1.25}
						stroke-opacity={on ? 1 : 0.35}
						stroke-dasharray={seg.available ? undefined : '3 3'}
						stroke-linejoin="round"
					/>
				{/each}
			{/each}
			{#each marks as m}
				<circle
					cx={x(stampOf(m.at))}
					cy={y(m.price)}
					r="3"
					fill={storeColors.of(m.store_id)}
					stroke="var(--color-background)"
					stroke-width="1.5"
				/>
			{/each}
			{#if hoverT != null}
				<line
					x1={x(hoverT)}
					x2={x(hoverT)}
					y1="0"
					y2={height}
					stroke="var(--color-muted-foreground)"
					stroke-opacity="0.5"
				/>
			{/if}
		</svg>
		{#if hoverT != null && readout.length}
			<div
				class="pointer-events-none absolute -top-1 z-10 -translate-y-full rounded-md border bg-popover px-2 py-1 text-xs whitespace-nowrap shadow-md"
				style:left="{Math.min(Math.max(x(hoverT) - 60, 0), Math.max(width - 140, 0))}px"
			>
				<div class="mb-0.5 text-muted-foreground">
					{fmtDateParts(new Date(hoverT).toISOString(), { day: 'numeric', month: 'short' })}
				</div>
				{#each readout as r (r.product_id)}
					<div class="flex items-center gap-1.5 {r.available ? '' : 'opacity-60'}">
						<span class="size-2 rounded-full" style:background-color={storeColors.of(r.store_id)}
						></span>
						<span>{storeColors.name(r.store_id)}</span>
						<span class="ml-auto pl-2 font-medium tabular-nums">{inrExact(r.price)}</span>
						{#if !r.available}<span class="text-muted-foreground">OOS</span>{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>
