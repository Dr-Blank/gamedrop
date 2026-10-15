<script>
	import { Search, TriangleAlert } from '@lucide/svelte';
	import { inspectJsonApi } from '$lib/api.js';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import StockBadge from './StockBadge.svelte';

	/** How the shop's product API maps onto a listing; `result` is a prior inspect. */
	let { baseUrl, collectionPath = '/', config = $bindable(null), result = null } = $props();

	const FIELDS = [
		['id', 'Id'],
		['title', 'Title'],
		['price', 'Price'],
		['sale_price', 'Sale price'],
		['compare_at', 'MRP / compare-at'],
		['available', 'In stock (flag or count)'],
		['preorder', 'Pre-order flag'],
		['image', 'Image'],
		['handle', 'Slug'],
		['url', 'Link (field, or /path/{slug})']
	];

	// svelte-ignore state_referenced_locally
	let inspected = $state(result);
	// svelte-ignore state_referenced_locally
	let apiUrl = $state(config?.endpoint ? new URL(config.endpoint, baseUrl).href : '');
	let busy = $state(false);
	let error = $state('');

	async function run(body) {
		busy = true;
		error = '';
		try {
			inspected = await inspectJsonApi({
				base_url: baseUrl,
				collection_path: collectionPath || '/',
				...body
			});
			config = inspected.config;
		} catch (e) {
			error = e.message;
		} finally {
			busy = false;
		}
	}

	const findFields = () => run({ api_url: apiUrl.trim() || null });
	const testMapping = () => run({ config });
	const money = (v) => (v == null ? '—' : v.toLocaleString('en-IN'));
</script>

<div class="space-y-3 rounded-md border p-3">
	<div class="space-y-1.5">
		<label for="json-api-url" class="text-xs font-medium text-muted-foreground">
			Product API URL
		</label>
		<div class="flex gap-2">
			<Input
				id="json-api-url"
				bind:value={apiUrl}
				placeholder="{baseUrl}/api/products"
				class="h-8 text-xs"
			/>
			<Button size="sm" variant="outline" onclick={findFields} disabled={busy} class="h-8 text-xs">
				<Search class="size-3.5" />
				{apiUrl.trim() ? 'Read fields' : 'Find API'}
			</Button>
		</div>
		{#if !config?.endpoint}
			<p class="text-[0.7rem] text-muted-foreground">
				Leave it blank to search the shop's scripts. If that finds nothing: open the shop's
				catalogue in your browser, open DevTools → Network → Fetch/XHR, reload, and copy the URL of
				the request whose response lists the products.
			</p>
		{/if}
	</div>

	{#if config}
		<details open={!inspected?.samples?.length || inspected?.warnings?.length > 0}>
			<summary class="cursor-pointer text-xs font-medium text-muted-foreground">Mapping</summary>
			<div class="mt-2 grid gap-2 sm:grid-cols-3">
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Endpoint</span>
					<Input bind:value={config.endpoint} class="h-8 text-xs" />
				</label>
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Item list at</span>
					<Input bind:value={config.items_path} placeholder="(root)" class="h-8 text-xs" />
				</label>
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Total at</span>
					<Input bind:value={config.total_path} placeholder="(none)" class="h-8 text-xs" />
				</label>
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Paging</span>
					<select
						bind:value={config.paging}
						class="h-8 w-full rounded-md border bg-background px-2 text-xs"
					>
						<option value="none">None</option>
						<option value="offset">Offset</option>
						<option value="page">Page number</option>
					</select>
				</label>
				{#if config.paging !== 'none'}
					<label class="space-y-1">
						<span class="text-[0.7rem] text-muted-foreground">
							{config.paging === 'offset' ? 'Offset' : 'Page'} param
						</span>
						<Input bind:value={config.page_param} class="h-8 text-xs" />
					</label>
					<label class="space-y-1">
						<span class="text-[0.7rem] text-muted-foreground">Page size param / size</span>
						<div class="flex gap-1">
							<Input bind:value={config.size_param} class="h-8 text-xs" />
							<Input type="number" bind:value={config.page_size} class="h-8 w-20 text-xs" />
						</div>
					</label>
				{/if}
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Category param</span>
					<Input bind:value={config.collection_param} placeholder="(none)" class="h-8 text-xs" />
				</label>
				<label class="space-y-1">
					<span class="text-[0.7rem] text-muted-foreground">Divide prices by</span>
					<Input type="number" bind:value={config.price_divisor} class="h-8 text-xs" />
				</label>
			</div>
			<div class="mt-3 grid gap-2 sm:grid-cols-3">
				{#each FIELDS as [key, label]}
					<label class="space-y-1">
						<span class="text-[0.7rem] text-muted-foreground">{label}</span>
						<Input bind:value={config.fields[key]} placeholder="—" class="h-8 text-xs" />
					</label>
				{/each}
			</div>
			<p class="mt-2 text-[0.7rem] text-muted-foreground">
				Paths are dotted, like <code class="rounded bg-muted px-1">images.0.url</code>. A category
				URL such as <code class="rounded bg-muted px-1">/collections/strategy</code> sends its last part
				as the category param.
			</p>
		</details>

		<Button size="sm" variant="outline" onclick={testMapping} disabled={busy} class="h-7 text-xs">
			{busy ? 'Reading…' : 'Test mapping'}
		</Button>
	{/if}

	{#if error}
		<p class="flex items-center gap-1 text-xs text-destructive">
			<TriangleAlert class="size-3.5" />
			{error}
		</p>
	{/if}

	{#if inspected}
		{#each inspected.warnings ?? [] as w}
			<p class="flex items-center gap-1 text-xs text-amber-600">
				<TriangleAlert class="size-3.5" />
				{w}
			</p>
		{/each}
		{#if inspected.samples?.length}
			<div class="space-y-1">
				<p class="text-xs text-muted-foreground">
					Check these against the shop{inspected.total != null
						? ` — ${inspected.total} items in all`
						: ''}:
				</p>
				<ul class="divide-y rounded-md border text-xs">
					{#each inspected.samples as s}
						<li class="flex items-center justify-between gap-2 px-2 py-1.5">
							{#if s.url}
								<a href={s.url} target="_blank" rel="noopener" class="truncate hover:underline">
									{s.title}
								</a>
							{:else}
								<span class="truncate">{s.title}</span>
							{/if}
							<span class="flex shrink-0 items-center gap-2 tabular-nums">
								{money(s.price)}
								{#if s.compare_at_price}
									<s class="text-muted-foreground">{money(s.compare_at_price)}</s>
								{/if}
								<StockBadge available={s.available} preorder={s.preorder} size="sm" />
							</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	{/if}
</div>
