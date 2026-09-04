<script>
	import { Carta, MarkdownEditor, Markdown } from 'carta-md';
	import DOMPurify from 'dompurify';
	import 'carta-md/default.css';
	import { Button } from '$lib/components/ui/button';
	import { NotebookPen, Check, X } from '@lucide/svelte';

	/**
	 * A markdown note that reads as prose until you click it. Editing is a
	 * deliberate mode so a stray click on a row never opens a text field.
	 *
	 * @type {{
	 *   value: string | null,
	 *   placeholder?: string,
	 *   onsave: (next: string) => void | Promise<void>
	 * }}
	 */
	let { value = null, placeholder = 'Add a note…', onsave } = $props();

	// One instance per note; the editor keeps its history and toolbar on it.
	const carta = new Carta({ sanitizer: (html) => DOMPurify.sanitize(html) });

	let editing = $state(false);
	let draft = $state('');
	let saving = $state(false);

	function edit() {
		draft = value ?? '';
		editing = true;
	}

	async function save() {
		saving = true;
		try {
			await onsave(draft);
			editing = false;
		} finally {
			saving = false;
		}
	}
</script>

{#if editing}
	<div class="space-y-2">
		<div class="markdown-note overflow-hidden rounded-lg border">
			<MarkdownEditor {carta} bind:value={draft} mode="tabs" placeholder="Markdown supported…" />
		</div>
		<div class="flex items-center gap-2">
			<Button size="sm" onclick={save} disabled={saving}>
				<Check class="size-3.5" /> Save note
			</Button>
			<Button size="sm" variant="ghost" onclick={() => (editing = false)} disabled={saving}>
				<X class="size-3.5" /> Cancel
			</Button>
		</div>
	</div>
{:else if value}
	<button
		onclick={edit}
		class="markdown-note w-full rounded-lg border border-dashed px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-muted/40"
		title="Edit note"
	>
		<Markdown {carta} {value} />
	</button>
{:else}
	<button
		onclick={edit}
		class="flex w-full items-center gap-1.5 rounded-lg border border-dashed px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
	>
		<NotebookPen class="size-3.5" />
		{placeholder}
	</button>
{/if}

<style>
	/* Carta ships a light-only theme; map it onto the app tokens. */
	.markdown-note :global(.carta-theme__default) {
		--border-color: var(--border);
		--hover-color: var(--muted);
		--caret-color: var(--foreground);
		--text-color: var(--foreground);
		--focus-outline: var(--ring);
	}
	/* Shiki emits dual-theme output with the dark colors parked in custom
	   properties; nothing swaps them in unless we do it here. */
	:global(html.dark) .markdown-note :global(.shiki),
	:global(html.dark) .markdown-note :global(.shiki span) {
		color: var(--shiki-dark) !important;
		background-color: transparent !important;
	}

	/* Carta ships unstyled prose; give it the density the rest of the app uses. */
	.markdown-note :global(.carta-font-code) {
		font-family: inherit;
		font-size: 0.8125rem;
		line-height: 1.5;
	}
	.markdown-note :global(.carta-renderer) {
		font-size: 0.8125rem;
		line-height: 1.55;
	}
	.markdown-note :global(.carta-renderer > :first-child) {
		margin-top: 0;
	}
	.markdown-note :global(.carta-renderer > :last-child) {
		margin-bottom: 0;
	}
	.markdown-note :global(.carta-renderer h1),
	.markdown-note :global(.carta-renderer h2),
	.markdown-note :global(.carta-renderer h3) {
		margin: 0.5em 0 0.25em;
		font-size: 0.9rem;
		font-weight: 600;
	}
	.markdown-note :global(.carta-renderer p) {
		margin: 0.35em 0;
	}
	.markdown-note :global(.carta-renderer ul),
	.markdown-note :global(.carta-renderer ol) {
		margin: 0.35em 0;
		padding-left: 1.15rem;
		list-style: revert;
	}
	.markdown-note :global(.carta-renderer a) {
		color: var(--primary);
		text-decoration: underline;
	}
	.markdown-note :global(.carta-renderer code) {
		border-radius: 0.25rem;
		background: var(--muted);
		padding: 0.1em 0.3em;
	}
	.markdown-note :global(.carta-renderer blockquote) {
		border-left: 2px solid var(--border);
		padding-left: 0.6rem;
		color: var(--muted-foreground);
	}
	/* The theme pins both panes to 600px; let them track the note instead. */
	.markdown-note :global(.carta-input),
	.markdown-note :global(.carta-renderer) {
		height: auto;
		min-height: 4rem;
		max-height: 60vh;
		overflow-y: auto;
		padding: 0.6rem 0.75rem;
	}
	.markdown-note :global(.carta-wrapper) {
		padding: 0;
	}
	.markdown-note :global(.carta-container > *) {
		margin: 0;
	}
	.markdown-note :global(.carta-input textarea::placeholder) {
		color: var(--muted-foreground);
	}
	.markdown-note :global(.carta-toolbar) {
		background: var(--muted);
	}
	.markdown-note :global(.carta-toolbar-left button.carta-active) {
		border-bottom-color: var(--primary);
	}
</style>
