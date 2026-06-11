<script>
	import { onMount } from 'svelte';
	import {
		getStores,
		addStore,
		patchStore,
		deleteStore,
		syncStore,
		syncAllStores,
		searchProducts,
		addWatchlist,
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

	// add store form
	let newStore = $state({
		id: '',
		name: '',
		type: 'shopify',
		base_url: '',
		collection_path: '/collections/board-games',
	});

	// scrape config editing — keyed by store id
	let editingConfig = $state({});   // store_id → { timeout_sec, request_delay_sec, sync_interval_hours }
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
		try { return JSON.parse(store.scrape_config); } catch { return {}; }
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
			newStore = { id: '', name: '', type: 'shopify', base_url: '', collection_path: '/collections/board-games' };
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
		} finally {
			syncingAll = false;
		}
	}

	async function remove(id) {
		if (!confirm(`Remove store "${id}"?`)) return;
		await deleteStore(id);
		await load();
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
			<Card.Content class="pt-4 space-y-1">
				{#each syncAllResults as r}
					<div class="text-sm flex items-center gap-2">
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
						<Table.Head></Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each stores as store}
						<Table.Row>
							<Table.Cell class="font-medium">{store.name}</Table.Cell>
							<Table.Cell><Badge variant="outline">{store.type}</Badge></Table.Cell>
							<Table.Cell class="text-sm">
								<a href={store.base_url} target="_blank" class="hover:underline text-muted-foreground">
									{store.base_url}
								</a>
							</Table.Cell>
							<Table.Cell class="text-sm min-w-64">
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
										<div class="flex gap-1 mt-1">
											<Button size="sm" onclick={() => saveCfg(store)} disabled={savingConfig[store.id]} class="h-6 text-xs">
												{savingConfig[store.id] ? 'Saving…' : 'Save'}
											</Button>
											<Button size="sm" variant="ghost" onclick={() => cancelEditCfg(store.id)} class="h-6 text-xs">
												Cancel
											</Button>
										</div>
									</div>
								{:else}
									{@const cfg = parseCfg(store)}
									<div class="text-muted-foreground space-y-0.5">
										<div>Timeout: {cfg.timeout_sec ?? 30}s</div>
										<div>Page delay: {cfg.request_delay_sec ?? 1}s</div>
										<div>Sync every: {cfg.sync_interval_hours ?? 6}h</div>
									</div>
									<Button size="sm" variant="ghost" onclick={() => startEditCfg(store)} class="h-6 text-xs mt-1 px-2">
										Edit
									</Button>
								{/if}
							</Table.Cell>
							<Table.Cell>
								<div class="flex flex-col gap-1 items-start">
									<div class="flex gap-2 items-center">
										<Button
											size="sm"
											variant="outline"
											onclick={() => sync(store.id)}
											disabled={syncing[store.id]}
										>
											{syncing[store.id] ? 'Syncing…' : 'Sync now'}
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
			<div class="flex gap-2 items-center">
				<select bind:value={newStore.type} class="border rounded px-3 py-2 text-sm bg-background">
					<option value="shopify">Shopify</option>
				</select>
				<Button onclick={submitAdd}>Add store</Button>
			</div>
			{#if addError}<p class="text-destructive text-sm">{addError}</p>{/if}
		</Card.Content>
	</Card.Root>

	<!-- Browse products -->
	<Card.Root>
		<Card.Header><Card.Title>Browse products</Card.Title></Card.Header>
		<Card.Content class="space-y-3">
			<div class="flex gap-2">
				<select bind:value={selectedStore} class="border rounded px-3 py-2 text-sm bg-background">
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
				<div class="border rounded-md divide-y max-h-96 overflow-y-auto">
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
