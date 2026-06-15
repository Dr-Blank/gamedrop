<script>
	import './layout.css';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { slide, fly } from 'svelte/transition';
	import {
		Home,
		Compass,
		TrendingDown,
		Sparkles,
		Heart,
		Store,
		Bell,
		Settings,
		ScrollText,
		EyeOff,
		Menu,
		X,
		Search,
		MoreHorizontal
	} from '@lucide/svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import Toaster from '$lib/components/Toaster.svelte';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { hidden } from '$lib/hidden.svelte.js';

	let { children } = $props();

	const primary = [
		{ href: '/', label: 'Home', icon: Home },
		{ href: '/browse', label: 'Browse', icon: Compass },
		{ href: '/drops', label: 'Drops', icon: TrendingDown },
		{ href: '/new', label: 'New', icon: Sparkles },
		{ href: '/watchlist', label: 'Watchlist', icon: Heart }
	];
	const more = [
		{ href: '/stores', label: 'Stores', icon: Store },
		{ href: '/notifications', label: 'Notifications', icon: Bell },
		{ href: '/hidden', label: 'Hidden', icon: EyeOff },
		{ href: '/settings', label: 'Settings', icon: Settings },
		{ href: '/logs', label: 'Logs', icon: ScrollText }
	];

	let mobileOpen = $state(false);
	let moreOpen = $state(false);
	let q = $state('');

	const path = $derived($page.url.pathname);
	const isActive = (/** @type {string} */ href) =>
		href === '/' ? path === '/' : path.startsWith(href);

	function submitSearch() {
		if (q.trim()) {
			goto(`/search?q=${encodeURIComponent(q.trim())}`);
			q = '';
			mobileOpen = false;
		}
	}

	onMount(() => {
		if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
		watchlist.load();
		hidden.load();
	});
</script>

<svelte:window onclick={() => (moreOpen = false)} />

<div class="min-h-[100dvh] bg-background text-foreground">
	<header
		class="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/60"
	>
		<div class="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:px-6">
			<a href="/" class="flex items-center gap-2 font-bold">
				<img src="/favicon.svg" alt="" class="size-6 rounded-md" />
				<span class="hidden sm:inline">GameDrop</span>
			</a>

			<!-- desktop nav -->
			<nav class="ml-2 hidden items-center gap-0.5 lg:flex">
				{#each primary as link}
					{@const Icon = link.icon}
					<a
						href={link.href}
						class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors {isActive(
							link.href
						)
							? 'bg-primary/10 font-medium text-primary'
							: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
					>
						<Icon class="size-4" />
						{link.label}
					</a>
				{/each}
			</nav>

			<!-- search -->
			<form
				onsubmit={(e) => {
					e.preventDefault();
					submitSearch();
				}}
				class="relative ml-auto hidden w-44 md:block xl:w-56"
			>
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
				/>
				<input
					bind:value={q}
					placeholder="Search…"
					class="h-9 w-full rounded-lg border bg-background pr-3 pl-8 text-sm shadow-sm transition-colors focus:ring-2 focus:ring-ring focus:outline-none"
				/>
			</form>

			<div class="ml-auto flex items-center gap-1 md:ml-1">
				<!-- More menu (desktop) -->
				<div class="relative hidden lg:block">
					<button
						onclick={(e) => {
							e.stopPropagation();
							moreOpen = !moreOpen;
						}}
						class="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
						aria-label="More"
					>
						<MoreHorizontal class="size-5" />
					</button>
					{#if moreOpen}
						<div
							transition:fly={{ y: -6, duration: 150 }}
							class="absolute right-0 mt-1 w-44 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg"
						>
							{#each more as link}
								{@const Icon = link.icon}
								<a
									href={link.href}
									class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors {isActive(
										link.href
									)
										? 'bg-primary/10 text-primary'
										: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
								>
									<Icon class="size-4" />
									{link.label}
								</a>
							{/each}
						</div>
					{/if}
				</div>

				<ThemeToggle />
				<button
					class="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
					onclick={() => (mobileOpen = !mobileOpen)}
					aria-label="Menu"
				>
					{#if mobileOpen}<X class="size-5" />{:else}<Menu class="size-5" />{/if}
				</button>
			</div>
		</div>

		<!-- mobile nav -->
		{#if mobileOpen}
			<nav class="border-t lg:hidden" transition:slide={{ duration: 200 }}>
				<div class="mx-auto max-w-6xl space-y-1 px-3 py-3">
					<form
						onsubmit={(e) => {
							e.preventDefault();
							submitSearch();
						}}
						class="relative mb-2"
					>
						<Search
							class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
						/>
						<input
							bind:value={q}
							placeholder="Search any game…"
							class="h-10 w-full rounded-lg border bg-background pr-3 pl-9 text-sm"
						/>
					</form>
					{#each [...primary, ...more] as link}
						{@const Icon = link.icon}
						<a
							href={link.href}
							onclick={() => (mobileOpen = false)}
							class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors {isActive(
								link.href
							)
								? 'bg-primary/10 font-medium text-primary'
								: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
						>
							<Icon class="size-4" />
							{link.label}
						</a>
					{/each}
				</div>
			</nav>
		{/if}
	</header>

	<main class="mx-auto max-w-6xl px-4 py-6 sm:px-6">
		{@render children()}
	</main>
</div>

<Toaster />
