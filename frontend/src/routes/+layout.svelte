<script>
	import './layout.css';
	import { page } from '$app/stores';

	let { children } = $props();

	const nav = [
		{ href: '/', label: 'Watchlist' },
		{ href: '/browse', label: 'Browse' },
		{ href: '/stores', label: 'Stores' },
		{ href: '/settings', label: 'Settings' },
	];
</script>

<div class="min-h-screen bg-background text-foreground">
	<nav class="border-b px-6 py-3 flex items-center gap-1">
		<span class="font-bold text-lg mr-4">🎲 Board Game Tracker</span>
		{#each nav as link}
			<a
				href={link.href}
				class="px-3 py-1.5 rounded-md text-sm transition-colors
					{$page.url.pathname === link.href
						? 'bg-primary text-primary-foreground font-medium'
						: 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
			>
				{link.label}
			</a>
		{/each}
	</nav>
	<main class="max-w-6xl mx-auto p-6">
		{@render children()}
	</main>
</div>
