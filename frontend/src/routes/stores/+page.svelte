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
		addWatchlist
	} from '$lib/api.js';
	import * as Card from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table';
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

	// add store form
	let newStore = $state({
		id: '',
		name: '',
		type: 'shopify',
		base_url: '',
		collection_path: '/collections/board-games'
	});

	// scrape config editing — keyed by store id
	let editingConfig = $state({}); // store_id → { timeout_sec, request_delay_sec, sync_interval_hours }
	let savingConfig = $state({});

	// product search
	let selectedStore = $state('');
	let productQuery = $state('');
	let products = $state([]);
	let productSearching = $state(false);

	async function load() {
		stores = await getStores();
		loading = false;
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
		try {
			await addStore(newStore);
			newStore = {
				id: '',
				name: '',
				type: 'shopify',
				base_url: '',
				collection_path: '/collections/board-games'
			};
			await load();
		} catch (e) {
			addError = e.message;
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

	async function watch(product) {
		await addWatchlist(product.id, null);
		alert(`"${product.title}" added to watchlist`);
	}

	function fmtDate(iso) {
		if (!iso) return 'Never';
		const d = new Date(iso);
		return d.toLocaleString();
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
		<Card.Root>
			<Card.Header><Card.Title>Configured stores</Card.Title></Card.Header>
			<Table.Root>
				<Table.Header>
					<Table.Row>
						<Table.Head>Name</Table.Head>
						<Table.Head>Type</Table.Head>
						<Table.Head>URL</Table.Head>
						<Table.Head>Scrape config</Table.Head>
						<Table.Head>Last sync</Table.Head>
						<Table.Head></Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each stores as store}
						<Table.Row>
							<Table.Cell class="font-medium">
								{store.name}
								{#if !store.enabled}
									<Badge variant="secondary" class="ml-1 text-xs">disabled</Badge>
								{/if}
							</Table.Cell>
							<Table.Cell><Badge variant="outline">{store.type}</Badge></Table.Cell>
							<Table.Cell class="text-sm">
								<a
									href={store.base_url}
									target="_blank"
									class="text-muted-foreground hover:underline"
								>
									{store.base_url}
								</a>
							</Table.Cell>
							<Table.Cell class="min-w-64 text-sm">
								{#if editingConfig[store.id]}
									<div class="flex flex-col gap-1">
										<label class="flex items-center gap-2">
											<span class="w-36 text-muted-foreground">Timeout (s)</span>
											<Input
												type="number"
												bind:value={editingConfig[store.id].timeout_sec}
												class="h-7 w-20 text-xs"
											/>
										</label>
										<label class="flex items-center gap-2">
											<span class="w-36 text-muted-foreground">Delay between pages (s)</span>
											<Input
												type="number"
												step="0.1"
												bind:value={editingConfig[store.id].request_delay_sec}
												class="h-7 w-20 text-xs"
											/>
										</label>
										<label class="flex items-center gap-2">
											<span class="w-36 text-muted-foreground">Sync interval (h)</span>
											<Input
												type="number"
												bind:value={editingConfig[store.id].sync_interval_hours}
												class="h-7 w-20 text-xs"
											/>
										</label>
										<div class="mt-1 flex gap-1">
											<Button
												size="sm"
												onclick={() => saveCfg(store)}
												disabled={savingConfig[store.id]}
												class="h-6 text-xs"
											>
												{savingConfig[store.id] ? 'Saving…' : 'Save'}
											</Button>
											<Button
												size="sm"
												variant="ghost"
												onclick={() => cancelEditCfg(store.id)}
												class="h-6 text-xs"
											>
												Cancel
											</Button>
										</div>
									</div>
								{:else}
									{@const cfg = parseCfg(store)}
									<div class="space-y-0.5 text-muted-foreground">
										<div>Timeout: {cfg.timeout_sec ?? 30}s</div>
										<div>Page delay: {cfg.request_delay_sec ?? 1}s</div>
										<div>Sync every: {cfg.sync_interval_hours ?? 6}h</div>
									</div>
									<Button
										size="sm"
										variant="ghost"
										onclick={() => startEditCfg(store)}
										class="mt-1 h-6 px-2 text-xs"
									>
										Edit
									</Button>
								{/if}
							</Table.Cell>
							<Table.Cell class="min-w-40 text-xs">
								{#if store.last_sync_error}
									<div class="font-medium text-destructive">✗ Error</div>
									<div
										class="max-w-48 truncate text-muted-foreground"
										title={store.last_sync_error}
									>
										{store.last_sync_error}
									</div>
								{:else if store.last_synced_at}
									<div class="text-green-600">✓ Done</div>
									<div class="text-muted-foreground">{fmtDate(store.last_synced_at)}</div>
								{:else}
									<span class="text-muted-foreground">Never synced</span>
								{/if}
							</Table.Cell>
							<Table.Cell>
								<div class="flex flex-col items-start gap-1">
									<div class="flex items-center gap-2">
										<Button
											size="sm"
											variant="outline"
											onclick={() => sync(store.id)}
											disabled={syncing[store.id]}
										>
											{syncing[store.id] ? 'Syncing…' : 'Sync now'}
										</Button>
										<Button
											size="sm"
											variant="ghost"
											onclick={() => toggleLogs(store.id)}
											class="text-xs"
										>
											{logsOpen[store.id] ? 'Hide logs' : 'Logs'}
										</Button>
										<Button size="sm" variant="destructive" onclick={() => remove(store.id)}>
											Remove
										</Button>
									</div>
									{#if syncResults[store.id]}
										<span class="text-xs text-muted-foreground">
											+{syncResults[store.id].new_products} new,
											{syncResults[store.id].price_changes} price changes
										</span>
									{/if}
									{#if logsOpen[store.id]}
										<div class="mt-2 w-full min-w-80">
											{#if logsLoading[store.id]}
												<span class="text-xs text-muted-foreground">Loading logs…</span>
											{:else if logsData[store.id]?.length === 0}
												<span class="text-xs text-muted-foreground">No sync history yet.</span>
											{:else if logsData[store.id]}
												<div class="max-h-48 divide-y overflow-y-auto rounded border text-xs">
													{#each logsData[store.id] as log}
														<div class="flex items-start gap-2 px-2 py-1.5">
															<span
																class="shrink-0 {log.error ? 'text-destructive' : 'text-green-600'}"
															>
																{log.error ? '✗' : '✓'}
															</span>
															<div class="min-w-0 flex-1">
																<div class="flex flex-wrap items-center gap-2">
																	<span class="font-medium">{fmtDate(log.started_at)}</span>
																	{#if log.finished_at}
																		<span class="text-muted-foreground"
																			>{fmtDuration(log.started_at, log.finished_at)}</span
																		>
																	{/if}
																</div>
																{#if log.error}
																	<div class="break-words text-destructive">{log.error}</div>
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
										</div>
									{/if}
								</div>
							</Table.Cell>
						</Table.Row>
					{/each}
				</Table.Body>
			</Table.Root>
		</Card.Root>
	{/if}

	<!-- Add store -->
	<Card.Root>
		<Card.Header><Card.Title>Add store</Card.Title></Card.Header>
		<Card.Content class="space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<Input bind:value={newStore.id} placeholder="ID (e.g. my-store)" />
				<Input bind:value={newStore.name} placeholder="Display name" />
				<Input bind:value={newStore.base_url} placeholder="https://store.com" />
				<Input bind:value={newStore.collection_path} placeholder="/collections/board-games" />
			</div>
			<div class="flex items-center gap-2">
				<select bind:value={newStore.type} class="rounded border bg-background px-3 py-2 text-sm">
					<option value="shopify">Shopify</option>
				</select>
				<Button onclick={submitAdd}>Add store</Button>
			</div>
			{#if addError}<p class="text-sm text-destructive">{addError}</p>{/if}
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
								<Button size="sm" variant="outline" href="/prices/{p.id}">History</Button>
								<Button size="sm" onclick={() => watch(p)}>+ Watch</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
