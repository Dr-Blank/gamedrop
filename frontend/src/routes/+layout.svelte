<script>
	import './layout.css';
	import { page } from '$app/stores';
	import { goto, onNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import { slide, fly } from 'svelte/transition';
	import {
		Home,
		Compass,
		TrendingDown,
		Sparkles,
		Heart,
		Store,
		Settings,
		ScrollText,
		EyeOff,
		Link2,
		Merge,
		Menu,
		X,
		Search,
		Keyboard,
		MoreHorizontal
	} from '@lucide/svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import NotificationBell from '$lib/components/NotificationBell.svelte';
	import { DROPS_URL, NEW_URL } from '$lib/browse.js';
	import Toaster from '$lib/components/Toaster.svelte';
	import ShortcutHelp from '$lib/components/ShortcutHelp.svelte';
	import { shortcuts } from '$lib/shortcuts.svelte.js';
	import { watchlist } from '$lib/watchlist.svelte.js';
	import { hidden } from '$lib/hidden.svelte.js';
	import { notifications } from '$lib/notifications.svelte.js';
	import { storeColors } from '$lib/storeColors.svelte.js';

	let { children } = $props();

	const primary = [
		{ href: '/', label: 'Home', icon: Home },
		{ href: '/browse', label: 'Browse', icon: Compass },
		{ href: DROPS_URL, label: 'Drops', icon: TrendingDown },
		{ href: NEW_URL, label: 'New', icon: Sparkles },
		{ href: '/watchlist', label: 'Watchlist', icon: Heart }
	];
	const more = [
		{ href: '/merges', label: 'Merges', icon: Merge },
		{ href: '/stores', label: 'Stores', icon: Store },
		{ href: '/notifications', label: 'Notifications', icon: null },
		{ href: '/hidden', label: 'Hidden', icon: EyeOff },
		{ href: '/bgg-link', label: 'BGG Link', icon: Link2 },
		{ href: '/settings', label: 'Settings', icon: Settings },
		{ href: '/logs', label: 'Logs', icon: ScrollText },
		{ href: '/shortcuts', label: 'Shortcuts', icon: Keyboard }
	];

	let mobileOpen = $state(false);
	let moreOpen = $state(false);
	let q = $state('');
	/** @type {HTMLInputElement | null} */
	let searchInput = $state(null);
	/** @type {HTMLInputElement | null} */
	let mobileSearchInput = $state(null);
	let searchFocused = $state(false);

	// The desktop search box is hidden under md — open the mobile nav instead so
	// the shortcut has something to focus on a phone.
	$effect(() =>
		shortcuts.registerSearchFocus(() => {
			if (searchInput?.offsetParent) {
				searchInput.select();
				return;
			}
			mobileOpen = true;
			setTimeout(() => mobileSearchInput?.select(), 0);
		})
	);

	const path = $derived($page.url.pathname);

	function isActive(/** @type {string} */ href) {
		const [hrefPath, hrefQuery] = href.split('?');
		if (hrefPath === '/') return path === '/';
		if (!path.startsWith(hrefPath)) return false;
		if (!hrefQuery) {
			// Plain /browse: only active when no f/s params (i.e. not a named preset)
			if (hrefPath === '/browse') {
				return !$page.url.searchParams.get('f') && !$page.url.searchParams.get('s');
			}
			return true;
		}
		// Parameterised link: all params must match current URL
		const want = new URLSearchParams(hrefQuery);
		for (const [k, v] of want) {
			if ($page.url.searchParams.get(k) !== v) return false;
		}
		return true;
	}

	function submitSearch() {
		if (q.trim()) {
			goto(`/search?q=${encodeURIComponent(q.trim())}`);
			q = '';
			mobileOpen = false;
		}
	}

	onNavigate((navigation) => {
		if (!document.startViewTransition) return;
		return new Promise((resolve) => {
			document.startViewTransition(async () => {
				resolve();
				await navigation.complete;
			});
		});
	});

	onMount(() => {
		if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
		watchlist.load();
		hidden.load();
		notifications.load();
		storeColors.load();
	});
</script>

<svelte:window onclick={() => (moreOpen = false)} onkeydown={(e) => shortcuts.handle(e)} />

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
					bind:this={searchInput}
					bind:value={q}
					onfocus={() => (searchFocused = true)}
					onblur={() => (searchFocused = false)}
					placeholder="Search…"
					aria-keyshortcuts="/ Control+K"
					class="h-9 w-full rounded-lg border bg-background pr-10 pl-8 text-sm shadow-sm transition-colors focus:ring-2 focus:ring-ring focus:outline-none"
				/>
				<!-- Hint, not a control: it would only be in the way once typing starts. -->
				{#if !searchFocused && !q}
					<kbd
						class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded border border-b-2 bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
						>/</kbd
					>
				{/if}
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
									{#if link.href === '/shortcuts'}
										<kbd
											class="ml-auto rounded border border-b-2 bg-muted px-1 font-mono text-[10px]"
											>?</kbd
										>
									{/if}
								</a>
							{/each}
						</div>
					{/if}
				</div>

				<NotificationBell />
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
							bind:this={mobileSearchInput}
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
							{#if Icon}
								<Icon class="size-4" />
							{:else}
								<!-- Notifications: show Bell with unread badge -->
								<span class="relative">
									<svg
										class="size-4"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path
											d="M13.73 21a2 2 0 0 1-3.46 0"
										/></svg
									>
									{#if notifications.unread > 0}
										<span class="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-red-500"
										></span>
									{/if}
								</span>
							{/if}
							{link.label}
							{#if link.href === '/notifications' && notifications.unread > 0}
								<span
									class="ml-auto rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-medium text-white"
									>{notifications.unread}</span
								>
							{/if}
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
<ShortcutHelp />

<style>
	/* Snappy fade for the page-level cross-fade; named elements morph natively */
	::view-transition-old(root),
	::view-transition-new(root) {
		animation-duration: 0.15s;
	}
</style>
