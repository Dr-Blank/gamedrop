import { describe, it, expect } from 'vitest';
import { REPO_URL, NEW_ISSUE_URL } from '$lib/repo.js';

describe('repo links', () => {
	it('exposes the repository URL', () => {
		expect(REPO_URL).toBe('https://github.com/Dr-Blank/gamedrop');
	});

	it('derives the new-issue URL from the repository URL', () => {
		expect(NEW_ISSUE_URL).toBe(`${REPO_URL}/issues/new`);
	});
});
