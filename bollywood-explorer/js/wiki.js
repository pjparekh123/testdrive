/* ═══════════════════════════════════════════════════════════════════
   PARDA · wiki.js
   Live posters & portraits from Wikipedia (CORS-friendly, no API key).
   Requests are coalesced into batched queries, resolved through
   redirects, and cached in localStorage so repeat visits are instant.
   ═══════════════════════════════════════════════════════════════════ */

window.Wiki = (function () {
  const API = "https://en.wikipedia.org/w/api.php";
  const CACHE_KEY = "parda-wiki-v1";
  const TTL = 1000 * 60 * 60 * 24 * 30; // 30 days

  let cache = {};
  try { cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); } catch (e) { cache = {}; }
  let saveTimer = null;
  function persist() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch (e) { /* quota — fine */ }
    }, 800);
  }

  function cacheGet(key) {
    const hit = cache[key];
    if (hit && Date.now() - hit.t < TTL) return hit.u; // string url or "" for confirmed miss
    return undefined;
  }
  function cacheSet(key, url) { cache[key] = { u: url || "", t: Date.now() }; persist(); }

  // ── batched thumbnail lookups ──────────────────────────────
  const pending = new Map(); // title -> {size, resolvers: []}
  let flushTimer = null;

  function lookup(title, size) {
    const key = size + "|" + title;
    const cached = cacheGet(key);
    if (cached !== undefined) return Promise.resolve(cached || null);
    return new Promise((resolve) => {
      const p = pending.get(key);
      if (p) { p.resolvers.push(resolve); return; }
      pending.set(key, { title, size, resolvers: [resolve] });
      clearTimeout(flushTimer);
      flushTimer = setTimeout(flush, 120);
    });
  }

  async function flush() {
    const jobs = Array.from(pending.values());
    pending.clear();
    // group by size, chunk by 40 titles
    const bySize = {};
    for (const j of jobs) (bySize[j.size] = bySize[j.size] || []).push(j);
    for (const size of Object.keys(bySize)) {
      const list = bySize[size];
      for (let i = 0; i < list.length; i += 40) {
        runBatch(list.slice(i, i + 40), Number(size));
      }
    }
  }

  async function runBatch(jobs, size) {
    const titles = jobs.map((j) => j.title).join("|");
    const url = API + "?" + new URLSearchParams({
      action: "query", format: "json", origin: "*",
      redirects: "1", prop: "pageimages", piprop: "thumbnail",
      pithumbsize: String(size), titles,
    });
    let data = null;
    try {
      const res = await fetch(url);
      if (res.ok) data = await res.json();
    } catch (e) { /* offline — resolve nulls below */ }

    // requested title -> final page title (normalization + redirects)
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
      if (data) cacheSet(size + "|" + j.title, found);
      for (const r of j.resolvers) r(found || null);
    }
  }

  // ── high-level helpers with fallback title cascades ────────
  async function firstHit(candidates, size) {
    for (const c of candidates) {
      const hit = await lookup(c, size);
      if (hit) return hit;
    }
    return null;
  }

  function posterCandidates(film) {
    const c = [];
    if (film.w) c.push(film.w);
    c.push(`${film.t} (${film.y} film)`);
    c.push(`${film.t} (film)`);
    c.push(film.t);
    return Array.from(new Set(c));
  }

  function personCandidates(name) {
    return [name, `${name} (actor)`, `${name} (actress)`, `${name} (director)`];
  }

  /** Attach a poster to <img>; toggles .loaded and hides fallback el. */
  function poster(film, imgEl, size) {
    firstHit(posterCandidates(film), size || 480).then((url) => {
      if (!url || !imgEl.isConnected) return;
      imgEl.onload = () => {
        imgEl.classList.add("loaded");
        const fb = imgEl.parentElement && imgEl.parentElement.querySelector("[data-fallback]");
        if (fb) fb.style.display = "none";
      };
      imgEl.src = url;
    });
  }

  /** Attach a portrait to <img> inside a .cast-ph bubble. */
  function person(name, imgEl) {
    firstHit(personCandidates(name), 240).then((url) => {
      if (!url || !imgEl.isConnected) return;
      imgEl.onload = () => { imgEl.classList.add("loaded"); };
      imgEl.src = url;
    });
  }

  /** Warm the cache for a list of films (fire-and-forget). */
  function prefetch(films) {
    for (const f of films) lookup(f.w || `${f.t} (${f.y} film)`, 480);
  }

  return { poster, person, prefetch };
})();
