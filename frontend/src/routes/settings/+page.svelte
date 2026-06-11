<script>
	import { onMount } from 'svelte';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';

	const API = '/api/settings';

	let form = $state({
		bgg_api_token: '',
		ntfy_server: '',
		ntfy_topic: '',
		ntfy_token: '',
	});
	let saving = $state(false);
	let saved = $state(false);
	let testBgg = $state({ loading: false, ok: null, message: '' });
	let testNtfy = $state({ loading: false, ok: null, message: '' });

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
			body: JSON.stringify(form),
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

	onMount(load);
</script>

<div class="space-y-6 max-w-2xl">
	<h1 class="text-2xl font-bold">Settings</h1>

	<!-- BGG API -->
	<Card.Root>
		<Card.Header>
			<Card.Title>BoardGameGeek API</Card.Title>
			<Card.Description>
				Required for ratings, rankings, and game data. Register at
				<a
					href="https://boardgamegeek.com/using_the_xml_api"
					target="_blank"
					class="underline"
				>boardgamegeek.com/using_the_xml_api</a> (must be logged in).
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-3">
			<div class="space-y-1">
				<label for="bgg-token" class="text-sm font-medium">API Token</label>
				<Input
					id="bgg-token"
					type="password"
					bind:value={form.bgg_api_token}
					placeholder={bggTokenSet ? '••••••••  (already set — paste new to replace)' : 'Paste your BGG bearer token'}
				/>
			</div>
			<div class="flex items-center gap-3">
				<Button variant="outline" onclick={runTestBgg} disabled={testBgg.loading}>
					{testBgg.loading ? 'Testing…' : 'Test connection'}
				</Button>
				{#if testBgg.message}
					<span class="text-sm {testBgg.ok ? 'text-green-600' : 'text-destructive'}">
						{testBgg.ok ? '✓' : '✗'} {testBgg.message}
					</span>
				{/if}
			</div>
		</Card.Content>
	</Card.Root>

	<!-- ntfy -->
	<Card.Root>
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
				<label for="ntfy-token" class="text-sm font-medium">Access token <span class="text-muted-foreground font-normal">(optional — only if your server requires auth)</span></label>
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
						{testNtfy.ok ? '✓' : '✗'} {testNtfy.message}
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

	<!-- Config file fallback note -->
	<Card.Root class="border-dashed">
		<Card.Content class="pt-4">
			<p class="text-sm text-muted-foreground">
				<strong>Headless / Docker deployment?</strong> All settings can also be set via environment variables
				in <code class="font-mono bg-muted px-1 rounded">backend/.env</code> —
				the UI takes priority if both are set.
			</p>
			<pre class="mt-2 text-xs bg-muted rounded p-3 font-mono">BGG_API_TOKEN=your_token
NTFY_SERVER=https://ntfy.example.com
NTFY_TOPIC=board-game-tracker
NTFY_TOKEN=optional_access_token</pre>
		</Card.Content>
	</Card.Root>
</div>
