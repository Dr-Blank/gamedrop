<script>
	import { toast } from '$lib/toast.svelte.js';
	import { flip } from 'svelte/animate';
	import { fly } from 'svelte/transition';
	import { CheckCircle2, XCircle, Info, X } from '@lucide/svelte';

	const icons = { success: CheckCircle2, error: XCircle, info: Info };
	const tone = {
		success: 'border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400',
		error: 'border-destructive/30 bg-destructive/10 text-destructive',
		info: 'border-border bg-card text-foreground'
	};
</script>

<div
	class="pointer-events-none fixed right-3 bottom-3 z-[100] flex w-[min(92vw,22rem)] flex-col gap-2"
>
	{#each toast.items as t (t.id)}
		{@const Icon = icons[t.kind]}
		<div
			animate:flip={{ duration: 250 }}
			in:fly={{ y: 16, duration: 250 }}
			out:fly={{ x: 24, duration: 200 }}
			class="pointer-events-auto flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur-sm {tone[
				t.kind
			]}"
			role="status"
		>
			<Icon class="mt-0.5 size-4 shrink-0" />
			<span class="flex-1 leading-snug">{t.message}</span>
			<button
				onclick={() => toast.dismiss(t.id)}
				class="-mr-1 rounded p-0.5 opacity-60 transition hover:opacity-100"
				aria-label="Dismiss"
			>
				<X class="size-3.5" />
			</button>
		</div>
	{/each}
</div>
