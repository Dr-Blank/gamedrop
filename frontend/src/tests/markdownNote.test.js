import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/svelte';

import MarkdownNote from '$lib/components/MarkdownNote.svelte';

/** Open the editor and hand back its textarea. */
async function open(props = {}) {
	const onsave = vi.fn();
	render(MarkdownNote, { value: null, onsave, ...props });
	await fireEvent.click(screen.getByRole('button', { name: /add a note/i }));
	const field = await waitFor(() => {
		const el = document.querySelector('textarea');
		if (!el) throw new Error('no editor');
		return el;
	});
	return { field, onsave };
}

describe('MarkdownNote', () => {
	it('puts the caret in the editor as soon as it opens', async () => {
		const { field } = await open();
		await waitFor(() => expect(document.activeElement).toBe(field));
	});

	it('saves on ctrl+enter', async () => {
		const { field, onsave } = await open();
		await fireEvent.input(field, { target: { value: 'sleeved copy' } });
		await fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true });
		await waitFor(() => expect(onsave).toHaveBeenCalledWith('sleeved copy'));
	});

	it('saves on meta+enter', async () => {
		const { field, onsave } = await open();
		await fireEvent.keyDown(field, { key: 'Enter', metaKey: true });
		await waitFor(() => expect(onsave).toHaveBeenCalled());
	});

	it('leaves a plain enter to the editor', async () => {
		const { field, onsave } = await open();
		await fireEvent.keyDown(field, { key: 'Enter' });
		expect(onsave).not.toHaveBeenCalled();
	});
});
