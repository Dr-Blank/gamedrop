const LINK_RE = /boardgamegeek\.com\/(?:boardgame|rpg|videogame)\/(\d+)/i;

/**
 * The game id inside a pasted BGG URL, or null.
 * @param {string|null|undefined} url
 */
export function parseBggId(url) {
	const m = LINK_RE.exec(url ?? '');
	return m ? Number(m[1]) : null;
}

/** @param {number|null|undefined} bggId */
export function bggGameUrl(bggId) {
	return bggId ? `https://boardgamegeek.com/boardgame/${bggId}` : null;
}

/** Web search for a game's BGG page — the shortest path to a link worth pasting. */
export function bggSearchUrl(title) {
	return `https://www.google.com/search?q=${encodeURIComponent(`BGG ${title}`)}`;
}
