<script>
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';
	import { getAppLogs, getGithubIssueExport } from '$lib/api.js';

	let records = $state([]);
	let loading = $state(true);
	let levelFilter = $state('');
	let issueText = $state('');
	let copied = $state(false);
	let logsCopied = $state(false);

	const NEW_ISSUE_URL = 'https://github.com/Dr-Blank/gamedrop/issues/new';
	const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
	const LEVEL_CLASS = {
		DEBUG: 'text-muted-foreground',
		INFO: 'text-blue-600',
		WARNING: 'text-amber-600',
		ERROR: 'text-red-600',
		CRITICAL: 'bg-red-600 text-white px-1 rounded'
	};

	async function load() {
		loading = true;
		records = await getAppLogs(levelFilter || undefined);
		loading = false;
	}

	async function exportIssue() {
		// Export whatever the user is currently viewing — '' means all levels.
		// (Previously forced ERROR, so with no errors the export was a bare template.)
		issueText = await getGithubIssueExport(levelFilter);
	}

	/** Plain-text rendering of the currently loaded records (respects level filter). */
	function recordsToText() {
		return records
			.map((r) => {
				const head = `[${r.ts}] ${r.level.padEnd(8)} ${r.logger}: ${r.msg}`;
				return r.exc ? `${head}\n${r.exc}` : head;
			})
			.join('\n');
	}

	async function copyLogs() {
		await navigator.clipboard.writeText(recordsToText());
		logsCopied = true;
		setTimeout(() => (logsCopied = false), 2000);
	}

	function downloadLogs() {
		const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
		const name = `gamedrop-logs-${levelFilter || 'all'}-${stamp}.txt`;
		const blob = new Blob([recordsToText()], { type: 'text/plain' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = name;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function copyIssue() {
		await navigator.clipboard.writeText(issueText);
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}

	// Logs are far too big for a query string — GitHub answers a prefilled body with
	// "Your request URL is too long" (414). Copy the report to the clipboard instead
	// and open a blank issue form for the user to paste into.
	async function openGithubIssue() {
		await copyIssue();
		window.open(NEW_ISSUE_URL, '_blank');
	}

	onMount(load);
</script>

<div class="space-y-4">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold">Application Logs</h1>
		<div class="flex gap-2">
			<select
				bind:value={levelFilter}
				onchange={load}
				class="rounded border bg-background px-3 py-2 text-sm"
			>
				{#each LEVELS as l}
					<option value={l}>{l || 'All levels'}</option>
				{/each}
			</select>
			<Button variant="outline" onclick={load}>Refresh</Button>
			<Button variant="outline" onclick={copyLogs} disabled={records.length === 0}>
				{logsCopied ? '✓ Copied' : 'Copy logs'}
			</Button>
			<Button variant="outline" onclick={downloadLogs} disabled={records.length === 0}>
				Download
			</Button>
			<Button variant="outline" onclick={exportIssue}>Export for GitHub</Button>
		</div>
	</div>

	{#if loading}
		<p class="text-muted-foreground">Loading…</p>
	{:else if records.length === 0}
		<p class="text-muted-foreground">No log records.</p>
	{:else}
		<Card.Root>
			<Card.Content class="p-0">
				<div class="max-h-[70vh] divide-y overflow-y-auto font-mono text-xs">
					{#each [...records].reverse() as r}
						<div class="flex gap-3 px-4 py-2 hover:bg-muted/30">
							<span class="shrink-0 text-muted-foreground"
								>{r.ts.replace('T', ' ').slice(0, 19)}</span
							>
							<span class="w-16 shrink-0 {LEVEL_CLASS[r.level] ?? ''}">{r.level}</span>
							<span class="w-40 shrink-0 truncate text-muted-foreground" title={r.logger}
								>{r.logger}</span
							>
							<div class="min-w-0 flex-1">
								<div class="break-words">{r.msg}</div>
								{#if r.exc}
									<pre class="mt-1 text-[10px] whitespace-pre-wrap text-red-500">{r.exc}</pre>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</Card.Content>
		</Card.Root>
	{/if}

	<!-- GitHub issue export panel -->
	{#if issueText}
		<Card.Root>
			<Card.Header>
				<Card.Title class="flex items-center justify-between">
					<span>GitHub Issue Export</span>
					<div class="flex gap-2">
						<Button size="sm" variant="outline" onclick={copyIssue}>
							{copied ? '✓ Copied' : 'Copy'}
						</Button>
						<Button size="sm" onclick={openGithubIssue}>Copy &amp; open GitHub ↗</Button>
					</div>
				</Card.Title>
			</Card.Header>
			<Card.Content class="space-y-2">
				<p class="text-xs text-muted-foreground">
					GitHub rejects prefilled issue bodies this long, so the report is copied to your clipboard
					— paste it into the issue form that opens.
				</p>
				<textarea
					class="w-full rounded border bg-muted/30 p-3 font-mono text-xs"
					rows="16"
					readonly
					value={issueText}
				></textarea>
			</Card.Content>
		</Card.Root>
	{/if}
</div>
