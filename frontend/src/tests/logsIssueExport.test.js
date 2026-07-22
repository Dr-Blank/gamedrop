import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api.js', () => ({
	getAppLogs: vi.fn(),
	getGithubIssueExport: vi.fn()
}));

import Logs from '../routes/logs/+page.svelte';
import * as api from '$lib/api.js';

// Long enough that a prefilled body would blow past GitHub's URL limit (414).
const LONG_REPORT = '### Logs\n' + 'ERROR gamedrop.sync: boom\n'.repeat(500);

async function renderLogs(issueText = LONG_REPORT) {
	api.getAppLogs.mockResolvedValue([
		{ ts: '2026-07-22T10:00:00', level: 'ERROR', logger: 'gamedrop.sync', msg: 'boom', exc: null }
	]);
	api.getGithubIssueExport.mockResolvedValue(issueText);
	render(Logs);
	await screen.findByText('boom');
	await fireEvent.click(screen.getByText('Export for GitHub'));
	await screen.findByText('GitHub Issue Export');
}

describe('logs page GitHub issue export', () => {
	let writeText;
	let open;

	beforeEach(() => {
		vi.clearAllMocks();
		writeText = vi.fn().mockResolvedValue(undefined);
		Object.assign(navigator, { clipboard: { writeText } });
		open = vi.fn();
		vi.stubGlobal('open', open);
	});

	it('opens a bare new-issue URL without a prefilled body', async () => {
		await renderLogs();
		await fireEvent.click(screen.getByText(/Copy & open GitHub/));

		await waitFor(() => expect(open).toHaveBeenCalled());
		const [url, target] = open.mock.calls[0];
		expect(url).toBe('https://github.com/Dr-Blank/gamedrop/issues/new');
		expect(url).not.toContain('body=');
		expect(url.length).toBeLessThan(2000);
		expect(target).toBe('_blank');
	});

	it('copies the report to the clipboard so the user can paste it', async () => {
		await renderLogs();
		await fireEvent.click(screen.getByText(/Copy & open GitHub/));

		await waitFor(() => expect(writeText).toHaveBeenCalledWith(LONG_REPORT));
	});
});
