// ==UserScript==
// @name         GameDrop
// @namespace    https://github.com/dr-blank/gamedrop
// @version      0.1.0
// @description  Cross-reference BGG ↔ local store prices
// @match        https://boardgamegeek.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_notification
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

'use strict';

const API_BASE = GM_getValue('api_base', 'http://localhost:8765/api');

function apiFetch(path) {
  return new Promise((resolve, reject) => {
    GM_xmlhttpRequest({
      method: 'GET',
      url: `${API_BASE}${path}`,
      onload: r => {
        try { resolve(JSON.parse(r.responseText)); }
        catch (e) { reject(e); }
      },
      onerror: reject,
    });
  });
}

// ── BGG game page ────────────────────────────────────────────────────────────
async function injectOnBggGame() {
  const match = location.pathname.match(/^\/boardgame\/(\d+)/);
  if (!match) return;
  const bggId = match[1];

  const panel = document.createElement('div');
  panel.id = 'gamedrop-panel';
  panel.style.cssText = `
    border: 1px solid #ccc; border-radius: 6px; padding: 12px;
    margin: 12px 0; background: #f9f9f9; font-size: 13px;
  `;
  panel.innerHTML = '<b>🏪 Store Prices</b> <span style="color:#888">loading…</span>';

  const target = document.querySelector('article') || document.querySelector('.game-header-body');
  if (target) target.insertAdjacentElement('afterend', panel);

  try {
    const results = await apiFetch(`/prices/search?q=${encodeURIComponent(document.title.split('|')[0].trim())}`);
    if (!results.length) {
      panel.innerHTML = '<b>🏪 Store Prices</b> <span style="color:#aaa">not listed in any tracked store</span>';
      return;
    }
    const rows = results.map(({ product, latest_price: lp }) => {
      const price = lp ? `₹${lp.price.toFixed(0)}` : '—';
      const stock = lp?.available ? '✅' : '❌ OOS';
      return `<tr>
        <td><a href="${product.url}" target="_blank">${product.title}</a></td>
        <td>${price}</td>
        <td>${stock}</td>
        <td><a href="/api/prices/product/${product.id}" target="_blank">history</a></td>
      </tr>`;
    }).join('');
    panel.innerHTML = `<b>🏪 Store Prices</b>
      <table style="width:100%;border-collapse:collapse;margin-top:8px">
        <tr style="font-weight:bold;border-bottom:1px solid #ddd">
          <td>Store</td><td>Price</td><td>Stock</td><td></td>
        </tr>${rows}
      </table>`;
  } catch (e) {
    panel.innerHTML = '<b>🏪 Store Prices</b> <span style="color:red">tracker offline</span>';
  }
}

// ── BGG collection / list view ───────────────────────────────────────────────
async function injectOnBggList() {
  // TODO: inject price column into collection table rows
  // Rows: tr[id^="row_"] — each has a data-objectid attribute with bgg_id
}

// ── Shopify store product page ───────────────────────────────────────────────
async function injectOnStoreProduct() {
  const titleEl = document.querySelector('h1.product__title, h1.product-single__title, h1[class*="product"]');
  if (!titleEl) return;
  const title = titleEl.textContent.trim();

  const panel = document.createElement('div');
  panel.style.cssText = `
    border: 1px solid #e2b900; border-radius: 6px; padding: 12px;
    margin: 12px 0; background: #fffde7; font-size: 13px;
  `;
  panel.innerHTML = '<b>🎲 BGG Rating</b> <span style="color:#888">loading…</span>';
  titleEl.insertAdjacentElement('afterend', panel);

  try {
    const results = await apiFetch(`/bgg/search?q=${encodeURIComponent(title)}`);
    if (!results.length) {
      panel.innerHTML = '<b>🎲 BGG</b> <span style="color:#aaa">not found on BGG</span>';
      return;
    }
    const top = results[0];
    const game = await apiFetch(`/bgg/game/${top.bgg_id}`);
    panel.innerHTML = `<b>🎲 BGG</b>
      <a href="${game.bgg_url}" target="_blank">${game.name}</a>
      (${game.year || '?'}) &nbsp;
      ⭐ <b>${parseFloat(game.avg_rating || 0).toFixed(1)}</b>/10 &nbsp;
      Rank: <b>#${game.rank || '?'}</b> &nbsp;
      Weight: <b>${parseFloat(game.avg_weight || 0).toFixed(1)}/5</b> &nbsp;
      👥 ${game.min_players}–${game.max_players}p`;
  } catch (e) {
    panel.innerHTML = '<b>🎲 BGG</b> <span style="color:red">tracker offline</span>';
  }
}

// ── Shopify collection page ──────────────────────────────────────────────────
async function injectOnStoreCollection() {
  // TODO: badge each product card with BGG rating
}

// ── Router ───────────────────────────────────────────────────────────────────
const host = location.hostname;
const path = location.pathname;

if (host === 'boardgamegeek.com') {
  if (path.match(/^\/boardgame\/\d+/)) injectOnBggGame();
  else if (path.startsWith('/collection/') || path.startsWith('/geeklists')) injectOnBggList();
} else {
  if (path.startsWith('/products/')) injectOnStoreProduct();
  else if (path.startsWith('/collections/')) injectOnStoreCollection();
}
