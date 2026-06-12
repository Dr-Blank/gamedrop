<script>
	import { theme } from '$lib/theme.svelte.js';
	import { Sun, Moon, Monitor } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';

	const order = /** @type {const} */ (['light', 'dark', 'system']);
	const icon = { light: Sun, dark: Moon, system: Monitor };
	const label = { light: 'Light', dark: 'Dark', system: 'System' };

	function cycle() {
		const next = order[(order.indexOf(theme.mode) + 1) % order.length];
		theme.set(next);
	}

	const Icon = $derived(icon[theme.mode]);
</script>

<Button
	variant="ghost"
	size="icon"
	onclick={cycle}
	title="Theme: {label[theme.mode]} (click to change)"
	aria-label="Toggle theme, current {label[theme.mode]}"
>
	{#key theme.mode}
		<span class="animate-in duration-200 zoom-in-50 spin-in-12">
			<Icon class="size-4" />
		</span>
	{/key}
</Button>
