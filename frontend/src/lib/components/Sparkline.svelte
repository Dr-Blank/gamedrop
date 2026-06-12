<script>
	// Compact price trend line. Accepts API history (newest-first) or a plain
	// number[] (oldest-first). Colour encodes direction: drop = good = emerald,
	// rise = rose, flat = muted.
	let {
		history = /** @type {Array<{price:number}>|number[]} */ ([]),
		width = 120,
		height = 36,
		class: className = ''
	} = $props();

	const prices = $derived.by(() => {
		if (!history?.length) return [];
		const arr = history.map((h) => (typeof h === 'number' ? h : h.price));
		// Heuristic: API gives newest-first → reverse to chronological.
		const looksApi = typeof history[0] === 'object';
		return looksApi ? arr.slice().reverse() : arr;
	});

	const trend = $derived(prices.length < 2 ? 0 : Math.sign(prices[prices.length - 1] - prices[0]));

	// trend: -1 drop (good) | 0 flat | 1 rise
	const stroke = $derived(
		trend < 0 ? '#10b981' : trend > 0 ? '#f43f5e' : 'var(--color-muted-foreground)'
	);

	const geom = $derived.by(() => {
		if (prices.length < 2) return null;
		const min = Math.min(...prices);
		const max = Math.max(...prices);
		const range = max - min || 1;
		const pad = 3;
		const pts = prices.map((p, i) => {
			const x = pad + (i / (prices.length - 1)) * (width - pad * 2);
			const y = pad + (1 - (p - min) / range) * (height - pad * 2);
			return [x, y];
		});
		const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
		const area = `${pad},${height} ${line} ${width - pad},${height}`;
		return { line, area, last: pts[pts.length - 1] };
	});

	const gid = `spark-${Math.random().toString(36).slice(2, 8)}`;
</script>

{#if geom}
	<svg
		viewBox="0 0 {width} {height}"
		{width}
		{height}
		class="block overflow-visible {className}"
		role="img"
		aria-label="Price trend"
	>
		<defs>
			<linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
				<stop offset="0%" stop-color={stroke} stop-opacity="0.22" />
				<stop offset="100%" stop-color={stroke} stop-opacity="0" />
			</linearGradient>
		</defs>
		<polygon points={geom.area} fill="url(#{gid})" />
		<polyline
			points={geom.line}
			fill="none"
			{stroke}
			stroke-width="1.75"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<circle cx={geom.last[0]} cy={geom.last[1]} r="2.4" fill={stroke} />
	</svg>
{/if}
