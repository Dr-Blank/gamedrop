import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import SortMenu from '$lib/components/SortMenu.svelte';

const fields = [
	{ name: 'title', label: 'Title', sortable: true },
	{ name: 'price', label: 'Price', sortable: true },
	{ name: 'available', label: 'Available', sortable: true },
	{ name: 'note', label: 'Note', sortable: false }
];

describe('SortMenu presets', () => {
	it('offers a preset only when the field can be sorted on', () => {
		render(SortMenu, { props: { fields } });
		expect(screen.getByRole('button', { name: 'Price low→high' })).toBeInTheDocument();
		// discount_pct is absent from the registry here.
		expect(screen.queryByRole('button', { name: 'Biggest discount' })).not.toBeInTheDocument();
	});

	it('applies a preset as the only sort', async () => {
		const onapply = vi.fn();
		render(SortMenu, { props: { fields, sorts: [{ field: 'title', dir: 'asc' }], onapply } });
		await fireEvent.click(screen.getByRole('button', { name: 'Price high→low' }));
		expect(onapply).toHaveBeenCalledOnce();
		expect(screen.getByRole('button', { name: 'Price high→low' })).toHaveAttribute(
			'aria-pressed',
			'true'
		);
	});

	it('clicking the active preset drops it', async () => {
		const onapply = vi.fn();
		render(SortMenu, { props: { fields, sorts: [{ field: 'price', dir: 'asc' }], onapply } });
		const preset = screen.getByRole('button', { name: 'Price low→high' });
		expect(preset).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(preset);
		expect(preset).toHaveAttribute('aria-pressed', 'false');
		expect(onapply).toHaveBeenCalledOnce();
	});

	it('marks nothing active once the sort list is built by hand', () => {
		render(SortMenu, {
			props: {
				fields,
				sorts: [
					{ field: 'available', dir: 'desc' },
					{ field: 'price', dir: 'asc' }
				]
			}
		});
		expect(screen.getByRole('button', { name: 'In stock first' })).toHaveAttribute(
			'aria-pressed',
			'false'
		);
	});
});

describe('SortMenu builder', () => {
	it('adds a row for the first unused sortable field', async () => {
		render(SortMenu, { props: { fields, sorts: [] } });
		await fireEvent.click(screen.getByRole('button', { name: /Add sort/ }));
		expect(screen.getByLabelText('Sort field')).toHaveValue('title');
	});

	it('reorders rows', async () => {
		render(SortMenu, {
			props: {
				fields,
				sorts: [
					{ field: 'title', dir: 'asc' },
					{ field: 'price', dir: 'asc' }
				]
			}
		});
		await fireEvent.click(screen.getAllByLabelText('Move sort up')[1]);
		const selects = screen.getAllByLabelText('Sort field');
		expect(selects[0]).toHaveValue('price');
		expect(selects[1]).toHaveValue('title');
	});

	it('removes a row', async () => {
		render(SortMenu, { props: { fields, sorts: [{ field: 'title', dir: 'asc' }] } });
		await fireEvent.click(screen.getByLabelText('Remove sort'));
		expect(screen.queryByLabelText('Sort field')).not.toBeInTheDocument();
	});

	it('clears every sort at once', async () => {
		const onapply = vi.fn();
		render(SortMenu, { props: { fields, sorts: [{ field: 'title', dir: 'asc' }], onapply } });
		await fireEvent.click(screen.getByRole('button', { name: /Clear/ }));
		expect(screen.queryByLabelText('Sort field')).not.toBeInTheDocument();
		expect(onapply).toHaveBeenCalledOnce();
	});
});
