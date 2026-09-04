import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

import Harness from './fixtures/FilterHarness.svelte';

const FIELDS = [
	{ name: 'last_change_at', label: 'Last Changed', type: 'datetime', ops: ['gte', 'lte'] }
];

function renderGroup(conditions = []) {
	let state;
	render(Harness, {
		props: {
			fields: FIELDS,
			initial: { type: 'group', op: 'and', conditions },
			onstate: (g) => (state = g)
		}
	});
	return () => state;
}

const dateCondition = (value) => [{ type: 'condition', field: 'last_change_at', op: 'gte', value }];

describe('date conditions', () => {
	it('edits a relative value as an amount, a unit and a direction', () => {
		renderGroup(dateCondition('-3w'));
		expect(screen.getByLabelText('Date mode')).toHaveValue('relative');
		expect(screen.getByLabelText('Date amount')).toHaveValue(3);
		expect(screen.getByLabelText('Date unit')).toHaveValue('w');
		expect(screen.getByLabelText('Date direction')).toHaveValue('ago');
	});

	it('takes an amount no preset list would have offered', async () => {
		const state = renderGroup(dateCondition('-1d'));
		await fireEvent.input(screen.getByLabelText('Date amount'), { target: { value: '17' } });
		expect(state().conditions[0].value).toBe('-17d');
	});

	it('changes the unit without losing the amount', async () => {
		const state = renderGroup(dateCondition('-17d'));
		await fireEvent.change(screen.getByLabelText('Date unit'), { target: { value: 'mo' } });
		expect(state().conditions[0].value).toBe('-17mo');
	});

	it('turns the offset around for a date in the future', async () => {
		const state = renderGroup(dateCondition('-2d'));
		await fireEvent.change(screen.getByLabelText('Date direction'), {
			target: { value: 'ahead' }
		});
		expect(state().conditions[0].value).toBe('+2d');
	});

	it('anchors to the start of today', async () => {
		const state = renderGroup(dateCondition('-1d'));
		await fireEvent.change(screen.getByLabelText('Date mode'), { target: { value: 'today' } });
		expect(state().conditions[0].value).toBe('today');
	});

	it('offers a date picker for an absolute value', () => {
		renderGroup(dateCondition('2026-06-01'));
		expect(screen.getByLabelText('Date mode')).toHaveValue('exact');
		expect(screen.queryByLabelText('Date amount')).not.toBeInTheDocument();
	});

	it('anchors to now without asking for an amount', async () => {
		const state = renderGroup(dateCondition('-1d'));
		await fireEvent.change(screen.getByLabelText('Date mode'), { target: { value: 'now' } });
		expect(state().conditions[0].value).toBe('now');
		expect(screen.queryByLabelText('Date amount')).not.toBeInTheDocument();
	});

	it('switching to an exact date replaces the offset with a real date', async () => {
		const state = renderGroup(dateCondition('-1d'));
		await fireEvent.change(screen.getByLabelText('Date mode'), { target: { value: 'exact' } });
		expect(state().conditions[0].value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
	});

	it('a new date condition starts relative rather than on a fixed day', async () => {
		const state = renderGroup();
		await fireEvent.click(screen.getByRole('button', { name: /^condition/ }));
		expect(state().conditions[0].value).toBe('-1d');
	});
});

describe('change windows', () => {
	const window_ = (since, until, include_new = false) => [
		{ type: 'change_window', since, until, include_new }
	];

	it('adds a window spanning the last week', async () => {
		const state = renderGroup();
		await fireEvent.click(screen.getByRole('button', { name: /change window/ }));
		expect(state().conditions[0]).toEqual({
			type: 'change_window',
			since: '-1w',
			until: 'now',
			include_new: true
		});
	});

	it('edits both bounds of an existing window', async () => {
		const state = renderGroup(window_('-1w', 'now'));

		await fireEvent.input(screen.getByLabelText('Window start amount'), {
			target: { value: '2' }
		});
		await fireEvent.change(screen.getByLabelText('Window start unit'), {
			target: { value: 'mo' }
		});
		await fireEvent.change(screen.getByLabelText('Window end mode'), {
			target: { value: 'relative' }
		});

		expect(state().conditions[0]).toEqual({
			type: 'change_window',
			since: '-2mo',
			until: '-1d',
			include_new: false
		});
	});

	it("toggles whether a shop's new listings count as changes", async () => {
		const state = renderGroup(window_('-1w', 'now'));

		await fireEvent.click(screen.getByLabelText(/count new listings/));

		expect(state().conditions[0].include_new).toBe(true);
	});

	it('explains what a window matches', () => {
		renderGroup(window_('-1w', 'now'));
		expect(screen.getByText(/not only the latest one/)).toBeInTheDocument();
	});

	it('takes the bounds either way round without complaining', () => {
		renderGroup(window_('now', '-1w'));
		expect(screen.getByText(/not only the latest one/)).toBeInTheDocument();
	});
});
