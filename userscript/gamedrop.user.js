// ==UserScript==
// @name         GameDrop
// @namespace    https://github.com/dr-blank/gamedrop
// @version      0.2.0
// @description  Cross-reference BGG ↔ local store prices, and sync shops from the browser
// @match        https://boardgamegeek.com/*
// @match        *://*/collections/*
// @match        *://*/products/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_notification
// @grant        GM_registerMenuCommand
// @connect      *
// @run-at       document-idle
// ==/UserScript==

'use strict';

const API_BASE = GM_getValue('api_base', 'http://localhost:8765/api');
const PAGE_GAP_MS = 3000;

GM_registerMenuCommand('Set GameDrop API address', () => {
  const next = window.prompt('GameDrop API address', API_BASE);
  if (next) GM_setValue('api_base', next.trim().replace(/\/+$/, ''));
});

function apiRequest(method, path, body) {
  return new Promise((resolve, reject) => {
    GM_xmlhttpRequest({
      method,
      url: `${API_BASE}${path}`,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      data: body ? JSON.stringify(body) : undefined,
      onload: r => {
        let data;
        try { data = JSON.parse(r.responseText); }
        catch (e) { return reject(e); }
        if (r.status >= 400) reject(new Error(data.detail || `HTTP ${r.status}`));
        else resolve(data);
      },
      onerror: reject,
    });
  });
}

const apiFetch = path => apiRequest('GET', path);

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

// ── Shopify sync from the browser ────────────────────────────────────────────
// For shops that refuse the server but still serve this browser: fetch
// products.json here and hand it to GameDrop.
const bareHost = h => h.toLowerCase().replace(/^www\./, '');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function trackedStore() {
  const stores = await apiFetch('/stores/');
  return stores.find(s => {
    try { return bareHost(new URL(s.base_url).hostname) === bareHost(location.hostname); }
    catch { return false; }
  });
}

async function fetchListing(collectionPath, report) {
  const products = [];
  const prefix = collectionPath === '/' ? '' : collectionPath.replace(/\/+$/, '');
  for (let page = 1; ; page++) {
    report(`${collectionPath} page ${page}…`);
    const r = await fetch(`${prefix}/products.json?limit=250&page=${page}`, { credentials: 'omit' });
    if (!r.ok) throw new Error(`${collectionPath} page ${page}: HTTP ${r.status}`);
    const batch = (await r.json()).products || [];
    if (!batch.length) return products;
    products.push(...batch);
    await sleep(PAGE_GAP_MS);
  }
}

function addSyncButton(store) {
  const btn = document.createElement('button');
  btn.textContent = `GameDrop: sync ${store.name}`;
  btn.style.cssText = `
    position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;
    padding: 8px 12px; border: 0; border-radius: 6px; font: 13px sans-serif;
    background: #4f46e5; color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.3);
    cursor: pointer;
  `;
  const report = text => { btn.textContent = text; };
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const paths = store.urls.filter(u => u.enabled).map(u => u.collection_path);
      const products = [];
      for (const p of paths) products.push(...await fetchListing(p, report));
      report(`Sending ${products.length} listings…`);
      const res = await apiRequest('POST', `/stores/${store.id}/import`, { products });
      report(`Synced: +${res.new_products} new, ${res.price_changes} changes`);
    } catch (e) {
      report(`Sync failed: ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
  document.body.appendChild(btn);
}

async function injectOnStore() {
  let store;
  try { store = await trackedStore(); }
  catch { return; }
  if (!store) return;
  if (store.type === 'shopify') addSyncButton(store);
  if (path.startsWith('/products/')) injectOnStoreProduct();
  else if (path.startsWith('/collections/')) injectOnStoreCollection();
}

// ── Router ───────────────────────────────────────────────────────────────────
const host = location.hostname;
const path = location.pathname;

if (host === 'boardgamegeek.com') {
  if (path.match(/^\/boardgame\/\d+/)) injectOnBggGame();
  else if (path.startsWith('/collection/') || path.startsWith('/geeklists')) injectOnBggList();
} else {
  injectOnStore();
}
