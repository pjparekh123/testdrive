#!/usr/bin/env node
/* ═══════════════════════════════════════════════════════════════════
   Curate real YouTube videos into data/videos.js
   ─────────────────────────────────────────────────────────────────
   A search link is a guess. This resolves an actual video id for each
   song, making-of and interview, so the site shows a real thumbnail and
   plays a real video instead of throwing the reader at a search page.

     YT_API_KEY=... node tools/fetch-videos.mjs
     YT_API_KEY=... node tools/fetch-videos.mjs --missing
     YT_API_KEY=... node tools/fetch-videos.mjs --since 1990
                    node tools/fetch-videos.mjs --audit

   Get a key at console.cloud.google.com → enable "YouTube Data API v3".
   The free quota is 10,000 units/day and a search costs 100, so roughly
   100 lookups a day: use --since / --missing to work through the book in
   batches. Everything already resolved is preserved between runs.

   Curation, not just search: results are scored, and the official label
   and archive channels below are strongly preferred — they hold the
   legitimate, complete, best-quality copies of this material. A result
   that looks like a fan re-upload, a reaction, or a clip loses out.
   ═══════════════════════════════════════════════════════════════════ */

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DATA = join(ROOT, "data");
const OUT = join(DATA, "videos.js");
const API = "https://youtube.googleapis.com/youtube/v3/search";
const KEY = process.env.YT_API_KEY;

const args = process.argv.slice(2);
const onlyMissing = args.includes("--missing");
const auditOnly = args.includes("--audit");
const sinceIdx = args.indexOf("--since");
const since = sinceIdx > -1 ? Number(args[sinceIdx + 1]) : 0;
const untilIdx = args.indexOf("--until");
const until = untilIdx > -1 ? Number(args[untilIdx + 1]) : 9999;

/* ── who actually owns this material ────────────────────────────
   Rights-holders and archives, weighted. Classic-era catalogue sits
   with the music labels; vintage on-set footage and star interviews
   are largely Lehren's archive and the public broadcaster's. */
const CHANNELS = [
  // music labels / studio catalogues
  ["shemaroo", 10], ["saregama", 10], ["ultra", 8], ["venus", 7],
  ["tips", 8], ["t-series", 8], ["yrf", 10], ["yash raj", 10],
  ["zee music", 8], ["sony music india", 8], ["eros", 7],
  ["rajshri", 9], ["goldmines", 6], ["pen movies", 7], ["nh studioz", 6],
  ["dharma", 8], ["red chillies", 8], ["bollywood classics", 7],
  ["filmigaane", 7], ["hungama", 5], ["speed records", 5],
  // archives, retrospectives, interviews
  ["lehren retro", 10], ["lehren", 7], ["film companion", 9],
  ["doordarshan", 9], ["prasar bharati", 9], ["rajya sabha", 7],
  ["nfdc", 8], ["film heritage", 9], ["mubi", 6], ["criterion", 6],
];
const JUNK = [
  "reaction", "review", "explained", "spoof", "parody", "remix by",
  "whatsapp status", "ringtone", "shorts", "ai cover", "fan made",
  "recreation", "dance cover", "karaoke", "lyrics only", "slowed",
];

function scoreItem(item, want) {
  const title = (item.snippet.title || "").toLowerCase();
  const chan = (item.snippet.channelTitle || "").toLowerCase();
  let s = 0;
  for (const [name, weight] of CHANNELS) if (chan.includes(name)) { s += weight; break; }
  for (const j of JUNK) if (title.includes(j) || chan.includes(j)) s -= 12;
  // reward the words we actually asked for
  for (const w of want) if (w.length > 3 && title.includes(w.toLowerCase())) s += 2;
  if (/official|full (video|song|movie)|original/.test(title)) s += 3;
  if (/\bhd\b|remastered|restored/.test(title)) s += 1;
  return s;
}

function loadFilms() {
  const window = { FILMS: {}, YEAR_NOTES: {}, ERAS: [] };
  window.registerFilms = (year, list) => {
    for (const f of list) f.y = year;
    window.FILMS[year] = (window.FILMS[year] || []).concat(list);
  };
  for (const file of readdirSync(DATA).filter((f) => /^films-.*\.js$/.test(f)).sort()) {
    new Function("window", readFileSync(join(DATA, file), "utf8"))(window);
  }
  const out = [];
  for (const y of Object.keys(window.FILMS)) for (const f of window.FILMS[y]) out.push(f);
  return out.filter((f) => f.y >= since && f.y <= until);
}

/* Every video this book wants, as {key, query, want}. */
function wantedFor(f) {
  const jobs = [];
  for (const song of (f.s || []).slice(0, 4)) {
    jobs.push({
      key: `${f.y}|${f.t}|song|${song}`,
      q: `${song} ${f.t} ${f.y} full video song`,
      want: [song, f.t],
    });
  }
  jobs.push({
    key: `${f.y}|${f.t}|bts`,
    q: `${f.t} ${f.y} making of behind the scenes rare footage`,
    want: [f.t, "making"],
  });
  jobs.push({
    key: `${f.y}|${f.t}|interview`,
    q: `${f.t} ${f.d || ""} ${(f.c || [])[0] || ""} interview`.replace(/\s+/g, " "),
    want: [f.t, "interview"],
  });
  return jobs;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function search(q, want) {
  const params = new URLSearchParams({
    key: KEY, part: "snippet", type: "video", maxResults: "8",
    q, relevanceLanguage: "hi", regionCode: "IN",
    videoEmbeddable: "true",          // only what we can actually play inline
    safeSearch: "moderate",
  });
  const res = await fetch(`${API}?${params}`);
  if (res.status === 403) {
    const body = await res.text();
    throw new Error(`quota or key problem: ${body.slice(0, 200)}`);
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = await res.json();
  const items = j.items || [];
  if (!items.length) return null;
  const best = items
    .map((it) => ({ it, s: scoreItem(it, want) }))
    .sort((a, b) => b.s - a.s)[0];
  if (best.s < 0) return null;                     // everything looked like junk
  return {
    id: best.it.id.videoId,
    title: best.it.snippet.title,
    channel: best.it.snippet.channelTitle,
    score: best.s,
  };
}

function loadExisting() {
  if (!existsSync(OUT)) return {};
  const w = {};
  new Function("window", readFileSync(OUT, "utf8"))(w);
  return w.VIDEOS || {};
}

function write(videos) {
  const keys = Object.keys(videos).sort();
  const body = keys.map((k) => `  ${JSON.stringify(k)}: ${JSON.stringify(videos[k])},`).join("\n");
  writeFileSync(OUT,
`/* Generated by tools/fetch-videos.mjs — do not edit by hand.
   Curated YouTube videos, keyed "year|title|kind[|song]".
   ${keys.length} videos as of ${new Date().toISOString().slice(0, 10)}. */
window.VIDEOS = {
${body}
};
`);
}

async function audit() {
  const videos = loadExisting();
  const keys = Object.keys(videos);
  if (!keys.length) return console.log("nothing curated yet");
  const byChannel = {};
  for (const k of keys) {
    const c = videos[k].c || "(unknown)";
    byChannel[c] = (byChannel[c] || 0) + 1;
  }
  console.log(`${keys.length} curated videos`);
  const kinds = {};
  for (const k of keys) { const kind = k.split("|")[2]; kinds[kind] = (kinds[kind] || 0) + 1; }
  console.log("by kind:", kinds);
  console.log("\ntop channels:");
  Object.entries(byChannel).sort((a, b) => b[1] - a[1]).slice(0, 18)
    .forEach(([c, n]) => console.log(`  ${String(n).padStart(4)}  ${c}`));
  const official = keys.filter((k) => {
    const c = (videos[k].c || "").toLowerCase();
    return CHANNELS.some(([n]) => c.includes(n));
  }).length;
  console.log(`\n${official}/${keys.length} (${Math.round(official / keys.length * 100)}%) come from a rights-holder or archive channel`);
}

async function main() {
  if (auditOnly) return audit();
  if (!KEY) {
    console.error("set YT_API_KEY (console.cloud.google.com → YouTube Data API v3)");
    process.exit(1);
  }
  const films = loadFilms();
  const videos = loadExisting();
  const jobs = films.flatMap(wantedFor).filter((j) => !(onlyMissing && videos[j.key]) && !videos[j.key]);
  console.log(`${films.length} films → ${jobs.length} videos to curate`);
  console.log(`(a search costs 100 quota units; the free daily allowance is 10,000)\n`);

  let found = 0, empty = 0;
  for (let i = 0; i < jobs.length; i++) {
    const j = jobs[i];
    try {
      const hit = await search(j.q, j.want);
      if (hit) {
        videos[j.key] = { v: hit.id, t: hit.title, c: hit.channel };
        found++;
        console.log(`✓ ${j.key}\n    ${hit.title}  —  ${hit.channel}`);
      } else { empty++; console.log(`· ${j.key} — nothing convincing`); }
    } catch (e) {
      console.error(`\n${e.message}`);
      console.error("stopping; everything resolved so far has been saved.");
      break;
    }
    if ((i + 1) % 25 === 0) write(videos);
    await sleep(120);
  }
  write(videos);
  console.log(`\ncurated ${found}, no good match for ${empty}. wrote ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
