// ==UserScript==
// @name         GameDrop
// @namespace    https://github.com/dr-blank/gamedrop
// @version      0.2.1
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

const log = (...args) => console.log('[GameDrop]', ...args);
const warn = (...args) => console.warn('[GameDrop]', ...args);
const logError = (...args) => console.error('[GameDrop]', ...args);
const snippet = text => (text || '').slice(0, 500);

GM_registerMenuCommand('Set GameDrop API address', () => {
  const next = window.prompt('GameDrop API address', API_BASE);
  if (next) GM_setValue('api_base', next.trim().replace(/\/+$/, ''));
});

function apiRequest(method, path, body) {
  const url = `${API_BASE}${path}`;
  return new Promise((resolve, reject) => {
    GM_xmlhttpRequest({
      method,
      url,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      data: body ? JSON.stringify(body) : undefined,
      onload: r => {
        let data = null;
        try { data = JSON.parse(r.responseText); }
        catch {}
        if (r.status >= 400 || data === null) {
          logError(`${method} ${url} → HTTP ${r.status}`, snippet(r.responseText));
        }
        if (r.status >= 400) reject(new Error(data?.detail || `HTTP ${r.status}`));
        else if (data === null) reject(new Error(`HTTP ${r.status}: not JSON`));
        else resolve(data);
      },
      onerror: r => {
        logError(`${method} ${url} → network error`, r);
        reject(new Error(`GameDrop API unreachable at ${API_BASE}`));
      },
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
  const matches = stores.filter(s => {
    try { return bareHost(new URL(s.base_url).hostname) === bareHost(location.hostname); }
    catch { return false; }
  });
  if (matches.length > 1) warn(`${matches.length} stores match this host; using ${matches[0].id}`, matches);
  return matches[0];
}

async function fetchListing(collectionPath, report) {
  const products = [];
  const prefix = collectionPath === '/' ? '' : collectionPath.replace(/\/+$/, '');
  for (let page = 1; ; page++) {
    report(`${collectionPath} page ${page}…`);
    const url = `${prefix}/products.json?limit=250&page=${page}`;
    const r = await fetch(url, { credentials: 'omit' });
    if (!r.ok) {
      logError(`GET ${url} → HTTP ${r.status}`, snippet(await r.text()));
      throw new Error(`${collectionPath} page ${page}: HTTP ${r.status}`);
    }
    const text = await r.text();
    let batch;
    try { batch = JSON.parse(text).products || []; }
    catch {
      logError(`GET ${url} → not JSON`, snippet(text));
      throw new Error(`${collectionPath} page ${page}: not JSON`);
    }
    log(`GET ${url} → ${batch.length} listings`);
    if (!batch.length) {
      if (page === 1) warn(`${collectionPath} returned no listings; check the store's listing URL`);
      return products;
    }
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
      log(`sync ${store.id}: paths`, paths, 'all URLs', store.urls);
      if (!paths.length) throw new Error('no enabled listing URLs');
      const products = [];
      const empty = [];
      for (const p of paths) {
        const batch = await fetchListing(p, report);
        if (!batch.length) empty.push(p);
        products.push(...batch);
      }
      // Shopify answers an unknown collection with an empty list, not a 404.
      if (!products.length) throw new Error(`no listings at ${empty.join(', ')}`);
      report(`Sending ${products.length} listings…`);
      log(`POST /stores/${store.id}/import: ${products.length} listings`);
      const res = await apiRequest('POST', `/stores/${store.id}/import`, { products });
      log(`sync ${store.id} done`, res);
      const note = empty.length ? ` (empty: ${empty.join(', ')})` : '';
      report(`Synced: +${res.new_products} new, ${res.price_changes} changes${note}`);
    } catch (e) {
      logError(`sync ${store.id} failed:`, e);
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
  catch (e) {
    warn('could not load tracked stores:', e.message);
    return;
  }
  if (!store) return;
  log(`tracked store ${store.id} (${store.type})`);
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
