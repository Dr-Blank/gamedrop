/** @param {number|null|undefined} n */
export function inr(n) {
	if (n == null) return '—';
	return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
