<script>
	import { onMount } from 'svelte';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { dateFormat, fmtDate } from '$lib/dateFormat.svelte.js';
	import { priceFormat, inr } from '$lib/priceFormat.svelte.js';

	const API = '/api/settings';

	const SECTIONS = [
		{ id: 'bgg', label: 'BoardGameGeek API' },
		{ id: 'ntfy', label: 'Push notifications' },
		{ id: 'dates', label: 'Date & time' },
		{ id: 'prices', label: 'Prices' },
		{ id: 'headless', label: 'Headless deployment' }
	];

	const DATE_FORMATS = [
		{ value: 'auto', label: 'Automatic', hint: 'follows your browser' },
		{ value: 'dmy', label: 'dd/mm/yyyy', hint: '' },
		{ value: 'mdy', label: 'mm/dd/yyyy', hint: '' },
		{ value: 'ymd', label: 'yyyy-mm-dd', hint: '' }
	];

	const PRICE_ROUNDING = [
		{ value: 'nearest-10', label: 'Rounded', hint: '₹1,999 → ₹2,000' },
		{ value: 'off', label: 'Exact', hint: '₹1,999' }
	];

	const CLOCK_FORMATS = [
		{ value: 'auto', label: 'Automatic', hint: 'follows your browser' },
		{ value: '24h', label: '24-hour', hint: '18:30' },
		{ value: '12h', label: '12-hour', hint: '6:30 PM' }
	];

	let form = $state({
		bgg_api_token: '',
		ntfy_server: '',
		ntfy_topic: '',
		ntfy_token: ''
	});
	let saving = $state(false);
	let saved = $state(false);
	let testBgg = $state({ loading: false, ok: null, message: '' });
	let testNtfy = $state({ loading: false, ok: null, message: '' });
	let activeSection = $state(SECTIONS[0].id);
	let now = $state(new Date().toISOString());

	async function load() {
		const res = await fetch(API).then((r) => r.json());
		// Don't overwrite masked values — keep placeholders
		form.ntfy_server = res.ntfy_server || '';
		form.ntfy_topic = res.ntfy_topic || '';
		form.bgg_api_token = res.bgg_api_token === '****' ? '' : res.bgg_api_token;
		form.ntfy_token = res.ntfy_token === '****' ? '' : res.ntfy_token;
		// Track whether tokens are already set (for display purposes)
		bggTokenSet = res.bgg_api_token === '****';
		ntfyTokenSet = res.ntfy_token === '****';
	}

	let bggTokenSet = $state(false);
	let ntfyTokenSet = $state(false);

	async function save() {
		saving = true;
		saved = false;
		await fetch(API, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(form)
		});
		saving = false;
		saved = true;
		setTimeout(() => (saved = false), 3000);
		await load();
	}

	async function runTestBgg() {
		testBgg = { loading: true, ok: null, message: '' };
		const res = await fetch('/api/settings/test/bgg', { method: 'POST' }).then((r) => r.json());
		testBgg = { loading: false, ok: res.ok, message: res.message };
	}

	async function runTestNtfy() {
		testNtfy = { loading: true, ok: null, message: '' };
		const res = await fetch('/api/settings/test/ntfy', { method: 'POST' }).then((r) => r.json());
		testNtfy = { loading: false, ok: res.ok, message: res.message };
	}

	onMount(() => {
		load();
		const observer = new IntersectionObserver(
			(entries) => {
				const top = entries
					.filter((e) => e.isIntersecting)
					.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
				if (top) activeSection = top.target.id;
			},
			{ rootMargin: '-80px 0px -55% 0px' }
		);
		for (const s of SECTIONS) {
			const el = document.getElementById(s.id);
			if (el) observer.observe(el);
		}
		return () => observer.disconnect();
	});
</script>

<div class="flex gap-8">
	<!-- Quick links -->
	<nav class="hidden w-48 shrink-0 lg:block">
		<div class="sticky top-6 space-y-1">
			<p class="px-3 pb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
				Settings
			</p>
			{#each SECTIONS as section}
				<a
					href="#{section.id}"
					class="block rounded-md px-3 py-1.5 text-sm transition-colors {activeSection ===
					section.id
						? 'bg-muted font-medium text-foreground'
						: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
				>
					{section.label}
				</a>
			{/each}
		</div>
	</nav>

	<div class="max-w-2xl min-w-0 flex-1 space-y-6">
		<h1 class="text-2xl font-bold">Settings</h1>

		<!-- BGG API -->
		<Card.Root id="bgg" class="scroll-mt-6">
			<Card.Header>
				<Card.Title>BoardGameGeek API</Card.Title>
				<Card.Description>
					Required for ratings, rankings, and game data. Register at
					<a href="https://boardgamegeek.com/using_the_xml_api" target="_blank" class="underline"
						>boardgamegeek.com/using_the_xml_api</a
					> (must be logged in).
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-3">
				<div class="space-y-1">
					<label for="bgg-token" class="text-sm font-medium">API Token</label>
					<Input
						id="bgg-token"
						type="password"
						bind:value={form.bgg_api_token}
						placeholder={bggTokenSet
							? '••••••••  (already set — paste new to replace)'
							: 'Paste your BGG bearer token'}
					/>
				</div>
				<div class="flex items-center gap-3">
					<Button variant="outline" onclick={runTestBgg} disabled={testBgg.loading}>
						{testBgg.loading ? 'Testing…' : 'Test connection'}
					</Button>
					{#if testBgg.message}
						<span class="text-sm {testBgg.ok ? 'text-green-600' : 'text-destructive'}">
							{testBgg.ok ? '✓' : '✗'}
							{testBgg.message}
						</span>
					{/if}
				</div>
			</Card.Content>
		</Card.Root>

		<!-- ntfy -->
		<Card.Root id="ntfy" class="scroll-mt-6">
			<Card.Header>
				<Card.Title>Push notifications (ntfy)</Card.Title>
				<Card.Description>
					Alerts for price drops, targets hit, and back-in-stock. Self-hosted or ntfy.sh.
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-3">
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1">
						<label for="ntfy-server" class="text-sm font-medium">Server URL</label>
						<Input id="ntfy-server" bind:value={form.ntfy_server} placeholder="https://ntfy.sh" />
					</div>
					<div class="space-y-1">
						<label for="ntfy-topic" class="text-sm font-medium">Topic</label>
						<Input id="ntfy-topic" bind:value={form.ntfy_topic} placeholder="board-game-tracker" />
					</div>
				</div>
				<div class="space-y-1">
					<label for="ntfy-token" class="text-sm font-medium"
						>Access token <span class="font-normal text-muted-foreground"
							>(optional — only if your server requires auth)</span
						></label
					>
					<Input
						id="ntfy-token"
						type="password"
						bind:value={form.ntfy_token}
						placeholder={ntfyTokenSet ? '••••••••  (already set)' : 'Leave blank if not required'}
					/>
				</div>
				<div class="flex items-center gap-3">
					<Button variant="outline" onclick={runTestNtfy} disabled={testNtfy.loading}>
						{testNtfy.loading ? 'Sending…' : 'Send test notification'}
					</Button>
					{#if testNtfy.message}
						<span class="text-sm {testNtfy.ok ? 'text-green-600' : 'text-destructive'}">
							{testNtfy.ok ? '✓' : '✗'}
							{testNtfy.message}
						</span>
					{/if}
				</div>
			</Card.Content>
		</Card.Root>

		<!-- Save -->
		<div class="flex items-center gap-3">
			<Button onclick={save} disabled={saving}>
				{saving ? 'Saving…' : 'Save settings'}
			</Button>
			{#if saved}
				<span class="text-sm text-green-600">✓ Saved</span>
			{/if}
		</div>

		<!-- Date & time -->
		<Card.Root id="dates" class="scroll-mt-6">
			<Card.Header>
				<Card.Title>Date &amp; time</Card.Title>
				<Card.Description>
					Dates follow your browser's region and clock automatically. Override it here only if you
					want a different order.
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-4">
				<div class="space-y-1.5">
					<p class="text-xs font-medium text-muted-foreground">Date order</p>
					<div class="flex flex-wrap gap-2">
						{#each DATE_FORMATS as option}
							<button
								onclick={() => dateFormat.set(option.value)}
								class="rounded-md border px-3 py-1.5 text-sm transition-colors {dateFormat.mode ===
								option.value
									? 'border-primary bg-primary/10 font-medium'
									: 'hover:bg-muted/50'}"
							>
								{option.label}
								{#if option.hint}
									<span class="block text-[0.7rem] font-normal text-muted-foreground">
										{option.hint}
									</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<div class="space-y-1.5">
					<p class="text-xs font-medium text-muted-foreground">Clock</p>
					<div class="flex flex-wrap gap-2">
						{#each CLOCK_FORMATS as option}
							<button
								onclick={() => dateFormat.setClock(option.value)}
								class="rounded-md border px-3 py-1.5 text-sm transition-colors {dateFormat.clock ===
								option.value
									? 'border-primary bg-primary/10 font-medium'
									: 'hover:bg-muted/50'}"
							>
								{option.label}
								{#if option.hint}
									<span class="block text-[0.7rem] font-normal text-muted-foreground">
										{option.hint}
									</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<p class="border-t pt-3 text-sm text-muted-foreground">
					Preview: <span class="font-medium text-foreground">{fmtDate(now)}</span>
				</p>
			</Card.Content>
		</Card.Root>

		<!-- Prices -->
		<Card.Root id="prices" class="scroll-mt-6">
			<Card.Header>
				<Card.Title>Prices</Card.Title>
				<Card.Description>
					A price ending in 9 reads smaller than it is, because the eye latches onto the leading
					digit. Rounding to the nearest ten takes that lean out. The price snapshot log keeps every
					reading exact either way, and nothing here changes what is stored, sorted, or alerted on.
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-4">
				<div class="space-y-1.5">
					<p class="text-xs font-medium text-muted-foreground">Displayed prices</p>
					<div class="flex flex-wrap gap-2">
						{#each PRICE_ROUNDING as option}
							<button
								onclick={() => priceFormat.set(option.value)}
								class="rounded-md border px-3 py-1.5 text-sm transition-colors {priceFormat.mode ===
								option.value
									? 'border-primary bg-primary/10 font-medium'
									: 'hover:bg-muted/50'}"
							>
								{option.label}
								{#if option.hint}
									<span class="block text-[0.7rem] font-normal text-muted-foreground">
										{option.hint}
									</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<p class="border-t pt-3 text-sm text-muted-foreground">
					Preview: <span class="font-medium text-foreground">{inr(1999)}</span>
				</p>
			</Card.Content>
		</Card.Root>

		<!-- Config file fallback note -->
		<Card.Root id="headless" class="scroll-mt-6 border-dashed">
			<Card.Header class="pb-2">
				<Card.Title class="text-base">Headless deployment</Card.Title>
			</Card.Header>
			<Card.Content>
				<p class="text-sm text-muted-foreground">
					<strong>Headless / Docker deployment?</strong> All settings can also be set via
					environment variables in <code class="rounded bg-muted px-1 font-mono">backend/.env</code>
					— the UI takes priority if both are set. Set
					<code class="rounded bg-muted px-1 font-mono">TZ</code> on the container so logs and sync times
					use your local clock.
				</p>
				<pre class="mt-2 rounded bg-muted p-3 font-mono text-xs">TZ=UTC
BGG_API_TOKEN=your_token
NTFY_SERVER=https://ntfy.example.com
NTFY_TOPIC=board-game-tracker
NTFY_TOKEN=optional_access_token</pre>
			</Card.Content>
		</Card.Root>
	</div>
</div>
