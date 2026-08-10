/* ═══════════════════════════════════════════════════════════════════
   PARDA · posters.js — real posters & portraits, resolved robustly.

   Sources are tried in order, and the <img> itself carries an error
   chain, so one dead URL never leaves a blank frame:

     1. data/posters.js  — URLs baked offline by tools/fetch-posters.mjs
                           (no network API at runtime; instant, permanent)
     2. Special:FilePath — direct image URL from a known File: name.
                           Plain <img>, so no CORS, works from file://
     3. MediaWiki pageimages API — resolves any of the 850 films by title
     4. REST summary API — second opinion when pageimages has no lead image
     5. a designed poster plate (poster-plate) drawn in CSS

   Notes on the API call, learned the hard way: prop=pageimages caps how
   many pages return image data per request, so pilimit MUST be set or a
   batch of 40 titles silently returns a handful of thumbnails. Misses are
   cached only briefly, never as permanent negatives.
   ═══════════════════════════════════════════════════════════════════ */

window.Posters = (function () {
  // Overridable so the site can be pointed at a Wikipedia mirror, or at a
  // local stub during testing.
  const ORIGIN = window.PARDA_WIKI_ORIGIN || "https://en.wikipedia.org";
  const API = ORIGIN + "/w/api.php";
  const REST = ORIGIN + "/api/rest_v1/page/summary/";
  const FILEPATH = ORIGIN + "/wiki/Special:FilePath/";
  const CACHE_KEY = "parda-img-v3";
  const TTL_HIT = 1000 * 60 * 60 * 24 * 30;   // 30 days for a real URL
  const TTL_MISS = 1000 * 60 * 10;            // 10 min only for a miss
  const BATCH = 45;                            // stay under the API's page cap

  const BAKED = window.POSTER_URLS || {};

  let cache = {};
  try { cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); } catch (e) { cache = {}; }
  let saveTimer = null;
  function persist() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch (e) { /* quota */ }
    }, 800);
  }
  function cacheGet(key) {
    const hit = cache[key];
    if (!hit) return undefined;
    const ttl = hit.u ? TTL_HIT : TTL_MISS;
    if (Date.now() - hit.t < ttl) return hit.u;
    delete cache[key];
    return undefined;
  }
  function cacheSet(key, url) { cache[key] = { u: url || "", t: Date.now() }; persist(); }

  /* ── batched pageimages lookups ────────────────────────────── */
  const pending = new Map();
  let flushTimer = null;

  function apiLookup(title, size) {
    const key = size + "|" + title;
    const cached = cacheGet(key);
    if (cached !== undefined) return Promise.resolve(cached || null);
    return new Promise((resolve) => {
      const p = pending.get(key);
      if (p) { p.resolvers.push(resolve); return; }
      pending.set(key, { title, size, resolvers: [resolve] });
      clearTimeout(flushTimer);
      flushTimer = setTimeout(flush, 90);
    });
  }

  function flush() {
    const jobs = Array.from(pending.values());
    pending.clear();
    const bySize = {};
    for (const j of jobs) (bySize[j.size] = bySize[j.size] || []).push(j);
    for (const size of Object.keys(bySize)) {
      const list = bySize[size];
      for (let i = 0; i < list.length; i += BATCH) {
        runBatch(list.slice(i, i + BATCH), Number(size));
      }
    }
  }

  async function runBatch(jobs, size) {
    const titles = jobs.map((j) => j.title).join("|");
    const params = new URLSearchParams({
      action: "query", format: "json", origin: "*",
      redirects: "1", prop: "pageimages", piprop: "thumbnail",
      pithumbsize: String(size),
      pilimit: "max",          // ← without this, most pages return no image
      titles,
    });
    let data = null;
    try {
      const res = await fetch(API + "?" + params.toString());
      if (res.ok) data = await res.json();
    } catch (e) { /* offline / blocked — resolve as unknown, not as miss */ }

    // requested title -> final page title (normalisation + redirects)
    const map = {};
    if (data && data.query) {
      for (const n of data.query.normalized || []) map[n.from] = n.to;
      for (const r of data.query.redirects || []) {
        for (const from of Object.keys(map)) if (map[from] === r.from) map[from] = r.to;
        map[r.from] = map[r.from] || r.to;
      }
    }
    const pages = {};
    if (data && data.query && data.query.pages) {
      for (const id of Object.keys(data.query.pages)) {
        const pg = data.query.pages[id];
        pages[pg.title] = (pg.thumbnail && pg.thumbnail.source) || "";
      }
    }
    for (const j of jobs) {
      const finalTitle = map[j.title] || j.title;
      const found = pages[finalTitle] || "";
      // Only record a result when the request actually succeeded.
      if (data) cacheSet(j.size + "|" + j.title, found);
      for (const r of j.resolvers) r(found || null);
    }
  }

  /* ── REST summary — a second opinion, also CORS-open ───────── */
  async function restLookup(title) {
    const key = "rest|" + title;
    const cached = cacheGet(key);
    if (cached !== undefined) return cached || null;
    try {
      const res = await fetch(REST + encodeURIComponent(title.replace(/ /g, "_")));
      if (!res.ok) { cacheSet(key, ""); return null; }
      const j = await res.json();
      const url = (j.originalimage && j.originalimage.source) ||
                  (j.thumbnail && j.thumbnail.source) || "";
      cacheSet(key, url);
      return url || null;
    } catch (e) { return null; }
  }

  /* ── candidate titles ──────────────────────────────────────── */
  function filmKey(f) { return f.y + "|" + f.t; }

  function filmTitles(f) {
    const out = [];
    if (f.w) out.push(f.w);
    if (f.y) {
      out.push(`${f.t} (${f.y} film)`);
      out.push(`${f.t} (${f.y} Hindi film)`);
    }
    out.push(`${f.t} (film)`, f.t);
    return Array.from(new Set(out));
  }

  function personTitles(name) {
    return [name, `${name} (actor)`, `${name} (actress)`, `${name} (director)`];
  }

  /* ── attach an image with a source chain ───────────────────── */
  /**
   * Walks `sources` (strings or async functions returning a URL) until one
   * actually decodes. Marks the <img> .loaded and hides the plate behind it.
   */
  function attach(imgEl, sources, onGiveUp) {
    let i = 0;
    let settled = false;

    function succeed() {
      if (settled) return;
      settled = true;
      imgEl.classList.add("loaded");
      const holder = imgEl.closest("[data-frame]") || imgEl.parentElement;
      const plate = holder && holder.querySelector("[data-fallback]");
      if (plate) plate.classList.add("is-hidden");
    }

    async function next() {
      if (settled || !imgEl.isConnected) return;
      if (i >= sources.length) { if (onGiveUp) onGiveUp(); return; }
      const src = sources[i++];
      let url = null;
      try { url = typeof src === "function" ? await src() : src; } catch (e) { url = null; }
      if (!url) return next();
      if (!imgEl.isConnected) return;
      imgEl.onload = succeed;
      imgEl.onerror = () => { imgEl.removeAttribute("src"); next(); };
      imgEl.src = url;
    }
    next();
  }

  /** Poster for a film. */
  function poster(film, imgEl, size) {
    if (!imgEl) return;
    size = size || 480;
    const titles = filmTitles(film);
    const sources = [];

    const baked = BAKED[filmKey(film)];
    if (baked) sources.push(baked);
    if (film.pf) sources.push(FILEPATH + encodeURIComponent(film.pf) + "?width=" + size);
    for (const t of titles) sources.push(() => apiLookup(t, size));
    sources.push(() => restLookup(titles[0]));

    attach(imgEl, sources);
  }

  /** Portrait for a person. */
  function person(name, imgEl) {
    if (!imgEl) return;
    const sources = personTitles(name).map((t) => () => apiLookup(t, 240));
    sources.push(() => restLookup(name));
    attach(imgEl, sources);
  }

  /* If nothing at all can be fetched — an offline machine, or a host that
     blocks external requests — say so once, quietly, rather than leaving
     the reader wondering why every frame is painted instead of photographed. */
  let noticeDone = false;
  function watchForBlockedImages() {
    if (noticeDone || Object.keys(BAKED).length) return;
    noticeDone = true;
    setTimeout(() => {
      if (document.querySelector("img.loaded")) return;
      if (document.getElementById("img-notice")) return;
      const el = document.createElement("div");
      el.id = "img-notice";
      el.innerHTML =
        `<span>Posters and portraits load from Wikipedia, which this page can't reach — ` +
        `you're seeing painted plates instead.</span><button aria-label="Dismiss">✕</button>`;
      el.querySelector("button").addEventListener("click", () => el.remove());
      document.body.appendChild(el);
    }, 6000);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchForBlockedImages);
  } else { watchForBlockedImages(); }

  return { poster, person };
})();

// Back-compat alias — earlier code called this Wiki.
window.Wiki = window.Posters;
