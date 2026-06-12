<script>
	import { onMount } from 'svelte';
	import { getWatchlist, patchWatchlistItem } from '$lib/api.js';
	import * as Card from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table';
	import { Badge } from '$lib/components/ui/badge';

	let watchlist = $state([]);
	let loading = $state(true);
	let error = $state('');

	async function load() {
		loading = true;
		try {
			watchlist = await getWatchlist();
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function toggle(id, field, value) {
		await patchWatchlistItem(id, { [field]: value });
		await load();
	}

	onMount(load);
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold">Notifications</h1>
		<p class="mt-1 text-sm text-muted-foreground">
			Configure what events trigger notifications. Notifications are sent via ntfy — configure your
			ntfy server in <a href="/settings" class="underline hover:text-foreground">Settings</a>.
		</p>
	</div>

	{#if loading}
		<p class="text-muted-foreground">Loading…</p>
	{:else if error}
		<p class="text-destructive">Error: {error}</p>
	{:else if watchlist.length === 0}
		<p class="text-muted-foreground">
			No items on watchlist. Add games from the <a href="/" class="underline hover:text-foreground"
				>Watchlist</a
			> page.
		</p>
	{:else}
		<Card.Root>
			<Table.Root>
				<Table.Header>
					<Table.Row>
						<Table.Head>Game</Table.Head>
						<Table.Head>Store</Table.Head>
						<Table.Head>Price / Stock</Table.Head>
						<Table.Head class="text-center">Price drop</Table.Head>
						<Table.Head class="text-center">Back in stock</Table.Head>
						<Table.Head class="text-center">Target price</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each watchlist as item}
						<Table.Row>
							<Table.Cell class="font-medium">
								<a href="/prices/{item.product.id}" class="hover:underline">{item.product.title}</a>
							</Table.Cell>
							<Table.Cell class="text-sm text-muted-foreground">
								{item.store?.name ?? item.product.store_id}
							</Table.Cell>
							<Table.Cell>
								<div class="flex items-center gap-2">
									{#if item.latest_price}
										<span class="font-semibold">₹{item.latest_price.price.toFixed(0)}</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
									{#if item.latest_price?.available}
										<Badge class="bg-green-100 text-green-800">In stock</Badge>
									{:else}
										<Badge variant="destructive">OOS</Badge>
									{/if}
								</div>
							</Table.Cell>
							<Table.Cell class="text-center">
								<input
									type="checkbox"
									class="h-4 w-4 cursor-pointer accent-primary"
									checked={item.watchlist.notify_price_drop ?? true}
									onchange={(e) => toggle(item.watchlist.id, 'notify_price_drop', e.target.checked)}
								/>
							</Table.Cell>
							<Table.Cell class="text-center">
								<input
									type="checkbox"
									class="h-4 w-4 cursor-pointer accent-primary"
									checked={item.watchlist.notify_back_in_stock ?? true}
									onchange={(e) =>
										toggle(item.watchlist.id, 'notify_back_in_stock', e.target.checked)}
								/>
							</Table.Cell>
							<Table.Cell class="text-center">
								<input
									type="checkbox"
									class="h-4 w-4 cursor-pointer accent-primary"
									checked={item.watchlist.notify_target_reached ?? true}
									onchange={(e) =>
										toggle(item.watchlist.id, 'notify_target_reached', e.target.checked)}
								/>
							</Table.Cell>
						</Table.Row>
					{/each}
				</Table.Body>
			</Table.Root>
		</Card.Root>
	{/if}
</div>
