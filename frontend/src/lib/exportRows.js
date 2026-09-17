/**
 * Rendering for browse exports. The backend returns one row per shop offer;
 * these turn that into something pasteable or saveable.
 *
 * Prices stay raw numbers — no symbol, no charm rounding — so whatever reads
 * the export can do arithmetic on them.
 */

const CSV_COLUMNS = [
	'game',
	'store',
	'price',
	'in_stock',
	'cheapest_in_stock_price',
	'cheapest_in_stock_store',
	'store_count',
	'watched',
	'in_cart',
	'owned'
];

/** @param {number|null|undefined} n */
function num(n) {
	return n == null ? '' : String(n);
}

/** @param {boolean} b */
function stock(b) {
	return b ? 'in stock' : 'out of stock';
}

/**
 * Markdown table of the four columns worth pasting into a chat.
 * @param {any[]} rows
 */
export function toMarkdown(rows) {
	const lines = ['| Game | Store | Price | Stock |', '| --- | --- | --- | --- |'];
	for (const r of rows) {
		lines.push(`| ${r.game} | ${r.store} | ${num(r.price)} | ${stock(r.in_stock)} |`);
	}
	return lines.join('\n');
}

/** @param {any} value */
function csvCell(value) {
	if (value == null) return '';
	if (typeof value === 'boolean') return value ? 'true' : 'false';
	const s = String(value);
	return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Full export as CSV text.
 * @param {any[]} rows
 */
export function toCsv(rows) {
	const lines = [CSV_COLUMNS.join(',')];
	for (const r of rows) {
		lines.push(CSV_COLUMNS.map((c) => csvCell(r[c])).join(','));
	}
	return lines.join('\n');
}

/** Timestamped file name, so repeated exports don't overwrite each other. */
export function csvFilename(label = 'browse') {
	const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
	const slug = label
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-|-$/g, '');
	return `gamedrop-${slug || 'browse'}-${stamp}.csv`;
}
