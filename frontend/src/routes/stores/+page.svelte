<script>
	import { onMount } from 'svelte';
	import {
		getStores,
		addStore,
		patchStore,
		deleteStore,
		syncStore,
		syncAllStores,
		getStoreLogs,
		searchProducts,
		getStoreTypes,
		detectStore
	} from '$lib/api.js';
	import { Check, ExternalLink, Search, TriangleAlert } from '@lucide/svelte';
	import { watchlist as watchStore } from '$lib/watchlist.svelte.js';
	import { storeColors } from '$lib/storeColors.svelte.js';
	import { toast } from '$lib/toast.svelte.js';
	import { fmtDate, fmtRelative } from '$lib/dateFormat.svelte.js';
	import { syncRunUrl } from '$lib/browse.js';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';

	let stores = $state([]);
	let loading = $state(true);
	let syncing = $state({});
	let syncingAll = $state(false);
	let syncResults = $state({});
	let syncAllResults = $state(null);
	let addError = $state('');
	let logsOpen = $state({});
	let logsData = $state({});
	let logsLoading = $state({});

	// add store form — URL first, everything else derived from what we detect
	const PLATFORM_LABELS = { shopify: 'Shopify', woocommerce: 'WooCommerce' };
	let storeTypes = $state([
		{ type: 'shopify', default_collection_path: '/collections/board-games' }
	]);
	let urlInput = $state('');
	let urlError = $state('');
	let detecting = $state(false);
	let detected = $state(null);
	let adding = $state(false);
	let newStore = $state({
		id: '',
		name: '',
		type: 'shopify',
		base_url: '',
		collection_path: '/collections/board-games'
	});

	function defaultPathFor(type) {
		return storeTypes.find((t) => t.type === type)?.default_collection_path ?? '/';
	}

	function normalizeUrl(raw) {
		const trimmed = raw.trim();
		if (!trimmed) return null;
		const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
		try {
			return new URL(withScheme);
		} catch {
			return null;
		}
	}

	async function runDetect() {
		const url = normalizeUrl(urlInput);
		if (!url || !url.hostname.includes('.')) {
			urlError = 'Enter a full shop URL, e.g. https://example-shop.com';
			return;
		}
		urlError = '';
		addError = '';
		detecting = true;
		try {
			const result = await detectStore(url.origin);
			detected = result;
			// A pasted category URL already says which listings to sync.
			const pastedPath = url.pathname.length > 1 ? url.pathname : '';
			newStore = {
				id: '',
				name: '',
				type: result.type ?? newStore.type,
				base_url: url.origin,
				collection_path:
					pastedPath || result.collection_path || defaultPathFor(result.type ?? newStore.type)
			};
		} catch (e) {
			urlError = e.message;
			detected = null;
		} finally {
			detecting = false;
		}
	}

	function resetAdd() {
		detected = null;
		urlInput = '';
		urlError = '';
		addError = '';
	}

	// scrape config editing — keyed by store id
	let editingConfig = $state({}); // store_id → { timeout_sec, request_delay_sec, sync_interval_hours }
	let savingConfig = $state({});

	// basic field editing — keyed by store id
	let editingBasic = $state({}); // store_id → { name, base_url, collection_path }
	let savingBasic = $state({});

	// product search
	let selectedStore = $state('');
	let productQuery = $state('');
	let products = $state([]);
	let productSearching = $state(false);

	async function load() {
		stores = await getStores();
		loading = false;
		try {
			storeTypes = await getStoreTypes();
		} catch {
			// Keep the built-in default list; the form still works.
		}
	}

	function parseCfg(store) {
		try {
			return JSON.parse(store.scrape_config);
		} catch {
			return {};
		}
	}

	function startEditCfg(store) {
		editingConfig[store.id] = { ...parseCfg(store) };
	}

	function cancelEditCfg(id) {
		delete editingConfig[id];
		editingConfig = { ...editingConfig };
	}

	function startEditBasic(store) {
		editingBasic[store.id] = {
			name: store.name,
			base_url: store.base_url,
			collection_path: store.collection_path
		};
	}

	function cancelEditBasic(id) {
		delete editingBasic[id];
		editingBasic = { ...editingBasic };
	}

	async function saveBasic(store) {
		savingBasic[store.id] = true;
		try {
			await patchStore(store.id, {
				name: editingBasic[store.id].name,
				base_url: editingBasic[store.id].base_url,
				collection_path: editingBasic[store.id].collection_path
			});
			await load();
			cancelEditBasic(store.id);
		} finally {
			savingBasic[store.id] = false;
		}
	}

	/** @param {string|null} hex null restores the colour derived from the store id */
	async function saveColor(store, hex) {
		storeColors.set(store.id, hex); // paint now; the reload only confirms
		try {
			await patchStore(store.id, { color: hex });
			await load();
		} catch (e) {
			storeColors.set(store.id, store.color ?? null);
			toast.error(e.message);
		}
	}

	async function saveCfg(store) {
		savingConfig[store.id] = true;
		try {
			await patchStore(store.id, { scrape_config: JSON.stringify(editingConfig[store.id]) });
			await load();
			cancelEditCfg(store.id);
		} finally {
			savingConfig[store.id] = false;
		}
	}

	async function submitAdd() {
		addError = '';
		const path = newStore.collection_path.trim();
		if (path && !path.startsWith('/')) {
			addError = 'Category path must start with /';
			return;
		}
		adding = true;
		try {
			// Blank name/id are filled in from the URL server-side.
			await addStore({
				...newStore,
				id: newStore.id.trim(),
				name: newStore.name.trim(),
				collection_path: path || '/'
			});
			resetAdd();
			await load();
		} catch (e) {
			addError = e.message;
		} finally {
			adding = false;
		}
	}

	async function sync(storeId) {
		syncing[storeId] = true;
		syncResults[storeId] = null;
		try {
			syncResults[storeId] = await syncStore(storeId);
			await load();
			if (logsOpen[storeId]) await loadLogs(storeId);
		} finally {
			syncing[storeId] = false;
		}
	}

	async function syncAll() {
		syncingAll = true;
		syncAllResults = null;
		try {
			const results = await syncAllStores();
			syncAllResults = results;
			await load();
		} finally {
			syncingAll = false;
		}
	}

	async function remove(id) {
		if (!confirm(`Remove store "${id}"?`)) return;
		await deleteStore(id);
		await load();
	}

	async function toggleLogs(storeId) {
		if (logsOpen[storeId]) {
			logsOpen[storeId] = false;
			return;
		}
		logsOpen[storeId] = true;
		await loadLogs(storeId);
	}

	async function loadLogs(storeId) {
		logsLoading[storeId] = true;
		try {
			logsData[storeId] = await getStoreLogs(storeId);
		} finally {
			logsLoading[storeId] = false;
		}
	}

	async function searchStore() {
		if (!selectedStore || !productQuery.trim()) return;
		productSearching = true;
		try {
			products = await searchProducts(selectedStore, productQuery);
		} finally {
			productSearching = false;
		}
	}

	function watch(product) {
		// Shared store handles add/remove + toast and keeps the button in sync.
		return watchStore.toggle({ product });
	}

	/** The category page a sync actually walks — base URL joined with the path. */
	function listingUrl(store) {
		try {
			return new URL(store.collection_path || '/', store.base_url).href;
		} catch {
			return store.base_url;
		}
	}

	function hostOf(url) {
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return url;
		}
	}

	function fmtDuration(startIso, endIso) {
		if (!startIso || !endIso) return '';
		const ms = new Date(endIso) - new Date(startIso);
		return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
	}

	onMount(load);
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold">Stores</h1>
		{#if stores.length > 0}
			<Button variant="outline" onclick={syncAll} disabled={syncingAll}>
				{syncingAll ? 'Syncing all…' : 'Sync all stores'}
			</Button>
		{/if}
	</div>

	{#if syncAllResults}
		<Card.Root>
			<Card.Content class="space-y-1 pt-4">
				{#each syncAllResults as r}
					<div class="flex items-center gap-2 text-sm">
						<span class="font-medium">{r.store_id}</span>
						{#if r.result.error}
							<span class="text-destructive">✗ {r.result.error}</span>
						{:else}
							<span class="text-green-600">
								✓ +{r.result.new_products} new, {r.result.price_changes} price changes
							</span>
						{/if}
					</div>
				{/each}
			</Card.Content>
		</Card.Root>
	{/if}

	<!-- Current stores -->
	{#if !loading && stores.length > 0}
		<div class="space-y-3">
			<h2 class="text-sm font-medium text-muted-foreground">Configured stores</h2>
			{#each stores as store}
				{@const cfg = parseCfg(store)}
				<Card.Root class="px-4 py-3">
					<div class="space-y-3">
						<div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
							<div class="flex min-w-0 items-center gap-2">
								<label
									class="relative size-5 shrink-0 cursor-pointer rounded-full ring-1 ring-border"
									style="background:{storeColors.of(store.id)}"
									title="Accent colour for {store.name}"
								>
									<input
										type="color"
										value={storeColors.of(store.id)}
										onchange={(e) => saveColor(store, e.currentTarget.value)}
										class="absolute inset-0 cursor-pointer opacity-0"
									/>
								</label>
								<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
									{#if editingBasic[store.id]}
										<Input bind:value={editingBasic[store.id].name} class="h-7 w-44 text-sm" />
									{:else}
										<span class="truncate font-medium">{store.name}</span>
									{/if}
									<Badge variant="outline" class="text-xs">{store.type}</Badge>
									{#if !store.enabled}
										<Badge variant="secondary" class="text-xs">disabled</Badge>
									{/if}
									{#if store.color}
										<button
											onclick={() => saveColor(store, null)}
											class="text-[0.65rem] text-muted-foreground hover:text-foreground"
										>
											reset colour
										</button>
									{/if}
								</div>
							</div>

							<div class="text-xs">
								{#if store.last_sync_error}
									<div class="font-medium text-destructive">✗ Sync failed</div>
									<div class="max-w-xs break-words text-muted-foreground">
										{store.last_sync_error}
									</div>
								{:else if store.last_synced_at}
									<div class="text-green-600">✓ Synced {fmtRelative(store.last_synced_at)}</div>
									<div class="text-muted-foreground">{fmtDate(store.last_synced_at)}</div>
								{:else}
									<span class="text-muted-foreground">Never synced</span>
								{/if}
							</div>
						</div>

						{#if editingBasic[store.id]}
							<div class="grid gap-2 sm:grid-cols-2">
								<label class="space-y-1">
									<span class="text-xs text-muted-foreground">Shop URL</span>
									<Input bind:value={editingBasic[store.id].base_url} class="h-8 text-xs" />
								</label>
								<label class="space-y-1">
									<span class="text-xs text-muted-foreground">Category path</span>
									<Input bind:value={editingBasic[store.id].collection_path} class="h-8 text-xs" />
								</label>
							</div>
						{:else}
							<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
								<a
									href={store.base_url}
									target="_blank"
									class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground hover:underline"
								>
									<ExternalLink class="size-3.5 shrink-0" />
									{hostOf(store.base_url)}
								</a>
								<a
									href={listingUrl(store)}
									target="_blank"
									title="Open the category page this store syncs"
									class="inline-flex min-w-0 items-center gap-1 text-muted-foreground hover:text-foreground hover:underline"
								>
									<ExternalLink class="size-3.5 shrink-0" />
									<span class="truncate">{store.collection_path}</span>
								</a>
							</div>
						{/if}

						{#if editingConfig[store.id]}
							<div class="space-y-2 rounded-md border p-3">
								<div class="grid gap-2 sm:grid-cols-3">
									<label class="space-y-1">
										<span class="text-xs text-muted-foreground">Timeout (s)</span>
										<Input
											type="number"
											bind:value={editingConfig[store.id].timeout_sec}
											class="h-8 text-xs"
										/>
									</label>
									<label class="space-y-1">
										<span class="text-xs text-muted-foreground">Page delay (s)</span>
										<Input
											type="number"
											step="0.1"
											bind:value={editingConfig[store.id].request_delay_sec}
											class="h-8 text-xs"
										/>
									</label>
									<label class="space-y-1">
										<span class="text-xs text-muted-foreground">Sync every (h)</span>
										<Input
											type="number"
											bind:value={editingConfig[store.id].sync_interval_hours}
											class="h-8 text-xs"
										/>
									</label>
								</div>
								<div class="flex gap-2">
									<Button
										size="sm"
										onclick={() => saveCfg(store)}
										disabled={savingConfig[store.id]}
										class="h-7 text-xs"
									>
										{savingConfig[store.id] ? 'Saving…' : 'Save'}
									</Button>
									<Button
										size="sm"
										variant="ghost"
										onclick={() => cancelEditCfg(store.id)}
										class="h-7 text-xs"
									>
										Cancel
									</Button>
								</div>
							</div>
						{:else}
							<div
								class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground"
							>
								<span>Timeout {cfg.timeout_sec ?? 30}s</span>
								<span>Page delay {cfg.request_delay_sec ?? 1}s</span>
								<span>Sync every {cfg.sync_interval_hours ?? 6}h</span>
								<button
									onclick={() => startEditCfg(store)}
									class="hover:text-foreground hover:underline"
								>
									Edit
								</button>
							</div>
						{/if}

						<div class="flex flex-wrap items-center gap-2 border-t pt-3">
							<Button
								size="sm"
								variant="outline"
								onclick={() => sync(store.id)}
								disabled={syncing[store.id]}
							>
								{syncing[store.id] ? 'Syncing…' : 'Sync now'}
							</Button>
							<Button size="sm" variant="ghost" onclick={() => toggleLogs(store.id)}>
								{logsOpen[store.id] ? 'Hide logs' : 'Logs'}
							</Button>
							{#if editingBasic[store.id]}
								<Button size="sm" onclick={() => saveBasic(store)} disabled={savingBasic[store.id]}>
									{savingBasic[store.id] ? 'Saving…' : 'Save'}
								</Button>
								<Button size="sm" variant="ghost" onclick={() => cancelEditBasic(store.id)}>
									Cancel
								</Button>
							{:else}
								<Button size="sm" variant="ghost" onclick={() => startEditBasic(store)}>
									Edit details
								</Button>
							{/if}
							<Button
								size="sm"
								variant="destructive"
								onclick={() => remove(store.id)}
								class="ml-auto"
							>
								Remove
							</Button>
						</div>

						{#if syncResults[store.id]}
							<p class="text-xs text-muted-foreground">
								+{syncResults[store.id].new_products} new, {syncResults[store.id].price_changes} price
								changes
							</p>
						{/if}

						{#if logsOpen[store.id]}
							{#if logsLoading[store.id]}
								<span class="text-xs text-muted-foreground">Loading logs…</span>
							{:else if logsData[store.id]?.length === 0}
								<span class="text-xs text-muted-foreground">No sync history yet.</span>
							{:else if logsData[store.id]}
								<div class="max-h-48 divide-y overflow-y-auto rounded-md border text-xs">
									{#each logsData[store.id] as log}
										<div class="flex items-start gap-2 px-2 py-1.5">
											<span class="shrink-0 {log.error ? 'text-destructive' : 'text-green-600'}">
												{log.error ? '✗' : '✓'}
											</span>
											<div class="min-w-0 flex-1">
												<div class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
													<span class="font-medium">{fmtDate(log.started_at)}</span>
													<span class="text-muted-foreground">{fmtRelative(log.started_at)}</span>
													{#if log.finished_at}
														<span class="text-muted-foreground">
															{fmtDuration(log.started_at, log.finished_at)}
														</span>
													{/if}
												</div>
												{#if log.error}
													<div class="break-words text-destructive">{log.error}</div>
												{:else if log.price_changes > 0}
													<a
														href={syncRunUrl(store.id, log)}
														title="Show the games that changed in this sync"
														class="text-muted-foreground hover:text-foreground hover:underline"
													>
														+{log.new_products} new · {log.price_changes} price changes
													</a>
												{:else}
													<div class="text-muted-foreground">
														+{log.new_products} new · {log.price_changes} price changes
													</div>
												{/if}
											</div>
										</div>
									{/each}
								</div>
							{/if}
						{/if}
					</div>
				</Card.Root>
			{/each}
		</div>
	{/if}

	<!-- Add store -->
	<Card.Root>
		<Card.Header class="pb-3">
			<Card.Title>Add store</Card.Title>
			<Card.Description>
				Paste the shop URL — or a category page URL — and the platform is detected for you.
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			<div class="space-y-1.5">
				<label for="add-url" class="text-xs font-medium text-muted-foreground">Shop URL</label>
				<div class="flex gap-2">
					<Input
						id="add-url"
						bind:value={urlInput}
						placeholder="https://example-shop.com/product-category/board-games/"
						oninput={() => {
							detected = null;
							addError = '';
						}}
						onkeydown={(e) => e.key === 'Enter' && runDetect()}
						aria-invalid={!!urlError}
					/>
					<Button variant="outline" onclick={runDetect} disabled={detecting || !urlInput.trim()}>
						<Search class="size-4 {detecting ? 'animate-pulse' : ''}" />
						{detecting ? 'Checking…' : 'Check'}
					</Button>
				</div>
				{#if urlError}
					<p class="flex items-center gap-1 text-xs text-destructive">
						<TriangleAlert class="size-3.5" />
						{urlError}
					</p>
				{/if}
			</div>

			{#if detected}
				<div
					class="space-y-2 rounded-lg border p-3 {detected.type
						? 'border-green-500/30 bg-green-500/5'
						: 'border-amber-500/30 bg-amber-500/5'}"
				>
					{#if detected.type}
						<p
							class="flex items-center gap-1.5 text-sm font-medium text-green-600 dark:text-green-400"
						>
							<Check class="size-4" />
							{PLATFORM_LABELS[detected.type] ?? detected.type} detected
						</p>
						{#if detected.sample_titles?.length}
							<ul class="space-y-0.5 text-xs text-muted-foreground">
								{#each detected.sample_titles.slice(0, 3) as t}
									<li class="truncate">· {t}</li>
								{/each}
							</ul>
						{/if}
					{:else}
						<p class="flex items-center gap-1.5 text-sm font-medium text-amber-600">
							<TriangleAlert class="size-4" /> Couldn't detect the platform
						</p>
						<p class="text-xs text-muted-foreground">{detected.detail}</p>
						<p class="text-xs text-muted-foreground">
							Pick a platform below and try a sync — it may just be blocking automated checks.
						</p>
					{/if}
					{#if detected.id_taken}
						<p class="flex items-center gap-1.5 text-xs text-amber-600">
							<TriangleAlert class="size-3.5" /> A store with id
							<code class="rounded bg-muted px-1">{detected.id}</code> already exists — change the id
							below.
						</p>
					{/if}
				</div>

				<div class="grid gap-3 sm:grid-cols-2">
					<div class="space-y-1.5">
						<label for="add-name" class="text-xs font-medium text-muted-foreground">
							Display name
						</label>
						<Input
							id="add-name"
							bind:value={newStore.name}
							placeholder={detected.name || 'Shop name'}
						/>
						<p class="text-[0.7rem] text-muted-foreground">
							Blank uses <span class="font-medium">{detected.name}</span>.
						</p>
					</div>
					<div class="space-y-1.5">
						<label for="add-id" class="text-xs font-medium text-muted-foreground">Store id</label>
						<Input id="add-id" bind:value={newStore.id} placeholder={detected.id || 'my-shop'} />
						<p class="text-[0.7rem] text-muted-foreground">
							Lowercase letters, numbers, dashes. Can't be changed later.
						</p>
					</div>
					<div class="space-y-1.5">
						<label for="add-type" class="text-xs font-medium text-muted-foreground">Platform</label>
						<select
							id="add-type"
							bind:value={newStore.type}
							onchange={() => (newStore.collection_path = defaultPathFor(newStore.type))}
							class="h-9 w-full rounded-md border bg-background px-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
						>
							{#each storeTypes as t}
								<option value={t.type}>{PLATFORM_LABELS[t.type] ?? t.type}</option>
							{/each}
						</select>
					</div>
					<div class="space-y-1.5">
						<label for="add-path" class="text-xs font-medium text-muted-foreground">
							Category path
						</label>
						<Input
							id="add-path"
							bind:value={newStore.collection_path}
							placeholder={defaultPathFor(newStore.type)}
						/>
						<p class="text-[0.7rem] text-muted-foreground">
							Leave <code class="rounded bg-muted px-1">/</code> to sync the whole catalog.
						</p>
					</div>
				</div>

				<div class="flex flex-wrap items-center gap-2 border-t pt-3">
					<Button onclick={submitAdd} disabled={adding}>
						{adding ? 'Adding…' : 'Add store'}
					</Button>
					<Button variant="ghost" onclick={resetAdd} disabled={adding}>Cancel</Button>
					<span class="text-xs text-muted-foreground">
						Nothing is fetched until you run a sync.
					</span>
				</div>
			{/if}

			{#if addError}
				<p class="flex items-center gap-1 text-sm text-destructive">
					<TriangleAlert class="size-4" />
					{addError}
				</p>
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Browse products -->
	<Card.Root>
		<Card.Header><Card.Title>Browse products</Card.Title></Card.Header>
		<Card.Content class="space-y-3">
			<div class="flex gap-2">
				<select bind:value={selectedStore} class="rounded border bg-background px-3 py-2 text-sm">
					<option value="">Select store…</option>
					{#each stores as s}<option value={s.id}>{s.name}</option>{/each}
				</select>
				<Input
					bind:value={productQuery}
					placeholder="Search products…"
					onkeydown={(e) => e.key === 'Enter' && searchStore()}
				/>
				<Button onclick={searchStore} disabled={productSearching}>
					{productSearching ? '…' : 'Search'}
				</Button>
			</div>

			{#if products.length > 0}
				<div class="max-h-96 divide-y overflow-y-auto rounded-md border">
					{#each products as p}
						<div class="flex items-center justify-between px-4 py-2 text-sm hover:bg-muted/50">
							<div>
								<a href={p.url} target="_blank" class="font-medium hover:underline">{p.title}</a>
							</div>
							<div class="flex items-center gap-3">
								<Button size="sm" variant="outline" href="/games/{p.game_id}">History</Button>
								<Button
									size="sm"
									variant={watchStore.has(p.id) ? 'secondary' : 'default'}
									onclick={() => watch(p)}
								>
									{watchStore.has(p.id) ? 'Watching' : '+ Watch'}
								</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
