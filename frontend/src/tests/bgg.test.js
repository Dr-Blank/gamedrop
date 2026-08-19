import { describe, it, expect } from 'vitest';
import { parseBggId, bggGameUrl, bggSearchUrl } from '$lib/bgg.js';

describe('parseBggId', () => {
	it('reads the id out of any BGG item URL', () => {
		expect(parseBggId('https://boardgamegeek.com/boardgame/13/catan')).toBe(13);
		expect(parseBggId('http://www.boardgamegeek.com/rpg/44/call-of-cthulhu')).toBe(44);
		expect(parseBggId('boardgamegeek.com/videogame/7')).toBe(7);
	});

	it('is null for anything else', () => {
		expect(parseBggId('https://example.com/boardgame/13')).toBeNull();
		expect(parseBggId('')).toBeNull();
		expect(parseBggId(null)).toBeNull();
	});
});

describe('bggGameUrl', () => {
	it('builds a game URL only for a real id', () => {
		expect(bggGameUrl(13)).toBe('https://boardgamegeek.com/boardgame/13');
		expect(bggGameUrl(null)).toBeNull();
	});
});

describe('bggSearchUrl', () => {
	it('searches the web for the game on BGG', () => {
		expect(bggSearchUrl('Catan')).toContain('BGG%20Catan');
	});
});
