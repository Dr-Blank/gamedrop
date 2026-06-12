<script>
	import './layout.css';
	import { page } from '$app/stores';

	let { children } = $props();

	const nav = [
		{ href: '/', label: 'Watchlist' },
		{ href: '/browse', label: 'Browse' },
		{ href: '/stores', label: 'Stores' },
		{ href: '/notifications', label: 'Notifications' },
		{ href: '/settings', label: 'Settings' },
		{ href: '/logs', label: 'Logs' }
	];
</script>

<div class="min-h-screen bg-background text-foreground">
	<nav class="flex items-center gap-1 border-b px-6 py-3">
		<span class="mr-4 text-lg font-bold">🎲 Board Game Tracker</span>
		{#each nav as link}
			<a
				href={link.href}
				class="rounded-md px-3 py-1.5 text-sm transition-colors
					{$page.url.pathname === link.href
					? 'bg-primary font-medium text-primary-foreground'
					: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
			>
				{link.label}
			</a>
		{/each}
	</nav>
	<main class="mx-auto max-w-6xl p-6">
		{@render children()}
	</main>
</div>
