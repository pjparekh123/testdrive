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
     node tools/fetch-posters.mjs --audit    # check what's baked actually loads

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
const auditOnly = process.argv.includes("--audit");

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

/* Ask the CDN whether every baked URL really serves an image, and report
   coverage by chapter — so gaps are known before the site goes public
   rather than discovered by a visitor. */
async function audit(films) {
  if (!existsSync(OUT)) { console.error("nothing baked yet — run without --audit first"); return; }
  const w = {};
  new Function("window", readFileSync(OUT, "utf8"))(w);
  const urls = w.POSTER_URLS || {};
  const keys = Object.keys(urls);
  console.log(`auditing ${keys.length} baked posters…\n`);

  let ok = 0; const dead = [];
  for (let i = 0; i < keys.length; i++) {
    const k = keys[i];
    try {
      const res = await fetch(urls[k], { method: "HEAD", headers: { "User-Agent": UA } });
      const type = res.headers.get("content-type") || "";
      if (res.ok && type.startsWith("image/")) ok++;
      else dead.push(`${k}  →  HTTP ${res.status} ${type}`);
    } catch (e) { dead.push(`${k}  →  ${e.message}`); }
    if ((i + 1) % 100 === 0) process.stdout.write(`  ${i + 1}/${keys.length}\r`);
    await sleep(40);
  }

  const byDecade = {};
  for (const f of films) {
    const d = Math.floor(f.y / 10) * 10;
    byDecade[d] = byDecade[d] || { total: 0, has: 0 };
    byDecade[d].total++;
    if (urls[`${f.y}|${f.t}`]) byDecade[d].has++;
  }
  console.log("\ncoverage by decade");
  for (const d of Object.keys(byDecade).sort()) {
    const { total, has } = byDecade[d];
    const pct = Math.round(has / total * 100);
    console.log(`  ${d}s  ${String(has).padStart(3)}/${String(total).padEnd(3)}  ${"█".repeat(Math.round(pct / 5)).padEnd(20)} ${pct}%`);
  }
  console.log(`\n${ok}/${keys.length} baked URLs serve a real image`);
  if (dead.length) {
    console.log(`\n${dead.length} broken:`);
    for (const d of dead.slice(0, 30)) console.log("  " + d);
    if (dead.length > 30) console.log(`  …and ${dead.length - 30} more`);
  }
  const noPoster = films.filter((f) => !urls[`${f.y}|${f.t}`]);
  if (noPoster.length) console.log(`\n${noPoster.length} films have no poster at all — these show a painted plate.`);
}

async function main() {
  const films = loadFilms();
  console.log(`${films.length} films across ${new Set(films.map((f) => f.y)).size} years`);
  if (auditOnly) return audit(films);

  // Always start from what's already baked. A run that can't reach the
  // network must never be able to wipe good data.
  let existing = {};
  if (existsSync(OUT)) {
    const w = {};
    new Function("window", readFileSync(OUT, "utf8"))(w);
    existing = w.POSTER_URLS || {};
    if (Object.keys(existing).length) {
      console.log(`keeping ${Object.keys(existing).length} already-resolved posters`);
    }
  }

  const results = { ...existing };
  let batchesOk = 0;
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
        batchesOk++;
        slice.forEach((f, n) => {
          const url = found[titles[n]];
          if (url) results[`${f.y}|${f.t}`] = url;
        });
      } catch (err) {
        console.warn(`  batch failed (${err.message}) — retrying once`);
        await sleep(2000);
        try {
          const found = await resolveBatch([...new Set(titles)]);
          batchesOk++;
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

  if (!batchesOk) {
    console.error("\nEvery request failed — no network route to en.wikipedia.org.");
    console.error("Nothing written, so any posters already baked are left untouched.");
    process.exit(1);
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
