#!/usr/bin/env node
/* ═══════════════════════════════════════════════════════════════════
   Bake real poster URLs into data/posters.js
   ─────────────────────────────────────────────────────────────────
   Resolves every film in data/films-*.js to its Wikipedia lead image
   (the poster) and writes a static lookup table, so the site needs no
   API call at runtime — posters appear instantly, and keep working
   from file://, offline hosts, and behind strict CSPs.

     node tools/fetch-posters.mjs            # resolve everything
     node tools/fetch-posters.mjs --missing  # only fill in gaps

   Re-run occasionally; Wikimedia thumbnail URLs are stable but the
   chosen lead image can change.
   ═══════════════════════════════════════════════════════════════════ */

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DATA = join(ROOT, "data");
const OUT = join(DATA, "posters.js");
const API = "https://en.wikipedia.org/w/api.php";
const SIZE = 640;
const BATCH = 45;            // pageimages caps pages per request
const PAUSE_MS = 250;        // be a polite API citizen
const UA = "Parda/1.0 (coffee-table book of Hindi cinema; educational)";

const onlyMissing = process.argv.includes("--missing");

/* ── load the film data by evaluating the browser files ─────── */
function loadFilms() {
  const window = { FILMS: {}, YEAR_NOTES: {}, ERAS: [] };
  window.registerFilms = (year, list) => {
    for (const f of list) f.y = year;
    window.FILMS[year] = (window.FILMS[year] || []).concat(list);
  };
  const files = readdirSync(DATA).filter((f) => /^films-.*\.js$/.test(f)).sort();
  for (const file of files) {
    const src = readFileSync(join(DATA, file), "utf8");
    new Function("window", src)(window);
  }
  const out = [];
  for (const y of Object.keys(window.FILMS)) for (const f of window.FILMS[y]) out.push(f);
  return out;
}

function titlesFor(f) {
  const t = [];
  if (f.w) t.push(f.w);
  t.push(`${f.t} (${f.y} film)`, `${f.t} (${f.y} Hindi film)`, `${f.t} (film)`, f.t);
  return [...new Set(t)];
}

async function resolveBatch(titles) {
  const params = new URLSearchParams({
    action: "query", format: "json", formatversion: "2",
    redirects: "1", prop: "pageimages", piprop: "thumbnail",
    pithumbsize: String(SIZE), pilimit: "max",
    titles: titles.join("|"),
  });
  const res = await fetch(`${API}?${params}`, { headers: { "User-Agent": UA } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  const json = await res.json();
  const q = json.query || {};

  const alias = {};                       // requested -> final title
  for (const n of q.normalized || []) alias[n.from] = n.to;
  for (const r of q.redirects || []) {
    for (const k of Object.keys(alias)) if (alias[k] === r.from) alias[k] = r.to;
    alias[r.from] = alias[r.from] || r.to;
  }
  const byTitle = {};
  for (const p of q.pages || []) {
    if (p.thumbnail && p.thumbnail.source) byTitle[p.title] = p.thumbnail.source;
  }
  const out = {};
  for (const t of titles) out[t] = byTitle[alias[t] || t] || null;
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const films = loadFilms();
  console.log(`${films.length} films across ${new Set(films.map((f) => f.y)).size} years`);

  let existing = {};
  if (onlyMissing && existsSync(OUT)) {
    const w = {};
    new Function("window", readFileSync(OUT, "utf8"))(w);
    existing = w.POSTER_URLS || {};
    console.log(`keeping ${Object.keys(existing).length} already-resolved posters`);
  }

  const results = { ...existing };
  // Round 1 uses each film's best title; later rounds retry the stragglers
  // with the next candidate, so one bad guess never loses a poster.
  const maxRounds = 4;
  for (let round = 0; round < maxRounds; round++) {
    const todo = films.filter((f) => {
      const key = `${f.y}|${f.t}`;
      return !results[key] && titlesFor(f)[round];
    });
    if (!todo.length) break;
    console.log(`\nround ${round + 1}: ${todo.length} to resolve`);

    for (let i = 0; i < todo.length; i += BATCH) {
      const slice = todo.slice(i, i + BATCH);
      const titles = slice.map((f) => titlesFor(f)[round]);
      try {
        const found = await resolveBatch([...new Set(titles)]);
        slice.forEach((f, n) => {
          const url = found[titles[n]];
          if (url) results[`${f.y}|${f.t}`] = url;
        });
      } catch (err) {
        console.warn(`  batch failed (${err.message}) — retrying once`);
        await sleep(2000);
        try {
          const found = await resolveBatch([...new Set(titles)]);
          slice.forEach((f, n) => {
            const url = found[titles[n]];
            if (url) results[`${f.y}|${f.t}`] = url;
          });
        } catch { /* leave for the next round */ }
      }
      process.stdout.write(`  ${Math.min(i + BATCH, todo.length)}/${todo.length}\r`);
      await sleep(PAUSE_MS);
    }
  }

  const got = Object.keys(results).length;
  const missing = films.filter((f) => !results[`${f.y}|${f.t}`]);
  console.log(`\n\nresolved ${got}/${films.length} posters (${(got / films.length * 100).toFixed(1)}%)`);
  if (missing.length) {
    console.log(`no image found for ${missing.length}:`);
    for (const f of missing.slice(0, 40)) console.log(`  ${f.y}  ${f.t}`);
    if (missing.length > 40) console.log(`  …and ${missing.length - 40} more`);
  }

  const sorted = Object.keys(results).sort();
  const body = sorted.map((k) => `  ${JSON.stringify(k)}: ${JSON.stringify(results[k])},`).join("\n");
  writeFileSync(OUT,
`/* Generated by tools/fetch-posters.mjs — do not edit by hand.
   Real poster images from Wikipedia, keyed "year|title".
   Resolved ${got} of ${films.length} films on ${new Date().toISOString().slice(0, 10)}. */
window.POSTER_URLS = {
${body}
};
`);
  console.log(`\nwrote ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
