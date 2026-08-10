#!/usr/bin/env node
/* ═══════════════════════════════════════════════════════════════════
   Bundle Parda into one self-contained HTML file.
   ─────────────────────────────────────────────────────────────────
   Inlines every stylesheet, script and data file so the book can be
   opened from a single file — handy for previews, email, or hosts
   that block external requests.

     node tools/bundle.mjs [fonts-inline.css] > parda.html
     node tools/bundle.mjs fonts-inline.css --embed-images > parda.html

   Pass a stylesheet of @font-face rules with base64 data: URIs to
   embed the typefaces too; otherwise the Google Fonts link is kept.

   --embed-images downloads every poster listed in data/posters.js and
   inlines it as a data: URI, producing a page that shows real posters
   with no external requests at all — the only way to get photographs
   onto a host that blocks outside traffic. Run fetch-posters.mjs first.
   Budget with --max-mb=N (default 14, to stay under a 16 MB ceiling).
   ═══════════════════════════════════════════════════════════════════ */

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const args = process.argv.slice(2);
const fontCssPath = args.find((a) => !a.startsWith("--"));
const embedImages = args.includes("--embed-images");
const maxBytes = Number((args.find((a) => a.startsWith("--max-mb=")) || "--max-mb=14").split("=")[1]) * 1048576;

/* Download each poster once and rewrite POSTER_URLS to data: URIs.
   Smallest files go first so a byte budget buys the most pictures. */
async function inlineImages(posterJs) {
  const w = {};
  new Function("window", posterJs)(w);
  const urls = w.POSTER_URLS || {};
  const keys = Object.keys(urls);
  if (!keys.length) {
    console.error("no posters in data/posters.js — run tools/fetch-posters.mjs first");
    return posterJs;
  }
  console.error(`fetching ${keys.length} posters…`);
  const fetched = new Map();
  let done = 0;
  for (const k of keys) {
    const url = urls[k];
    if (!fetched.has(url)) {
      try {
        const res = await fetch(url, { headers: { "User-Agent": "Parda/1.0 (bundler)" } });
        if (res.ok) {
          const buf = Buffer.from(await res.arrayBuffer());
          const type = res.headers.get("content-type") || "image/jpeg";
          fetched.set(url, { buf, type });
        } else fetched.set(url, null);
      } catch { fetched.set(url, null); }
    }
    if (++done % 50 === 0) console.error(`  ${done}/${keys.length}`);
  }
  const ranked = keys
    .map((k) => ({ k, hit: fetched.get(urls[k]) }))
    .filter((e) => e.hit)
    .sort((a, b) => a.hit.buf.length - b.hit.buf.length);

  const out = {};
  let used = 0, kept = 0;
  for (const { k, hit } of ranked) {
    const cost = Math.ceil(hit.buf.length * 4 / 3);
    if (used + cost > maxBytes) continue;
    out[k] = `data:${hit.type};base64,${hit.buf.toString("base64")}`;
    used += cost; kept++;
  }
  console.error(`inlined ${kept}/${keys.length} posters (${(used / 1048576).toFixed(1)} MB)`);
  return `window.POSTER_URLS = ${JSON.stringify(out)};`;
}

const html = read("index.html");

// pull the pieces out of index.html so the bundle can't drift from it
const cssFiles = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)">/g)].map((m) => m[1]);
const jsFiles = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
const bodyInner = html.match(/<body[^>]*>([\s\S]*?)<\/body>/)[1]
  .replace(/<script src="[^"]+"><\/script>\s*/g, "");
const title = html.match(/<title>([\s\S]*?)<\/title>/)[1];

const fontCss = fontCssPath && existsSync(fontCssPath)
  ? readFileSync(fontCssPath, "utf8")
  : null;

const css = cssFiles.map((f) => `/* ${f} */\n${read(f)}`).join("\n\n");
const jsParts = [];
for (const f of jsFiles) {
  let src = read(f);
  if (embedImages && f.endsWith("posters.js") && f.startsWith("data/")) {
    src = await inlineImages(src);
  }
  jsParts.push(`/* ${f} */\n${src}`);
}
const js = jsParts.join("\n;\n");

// The artifact host supplies <html>/<head>/<body>, so emit page content
// only. app.js stamps data-era onto the real <body> at route time, which
// is what the per-chapter theming keys off.
process.stdout.write(`<title>${title}</title>
<style>
${fontCss || "@import url('https://fonts.googleapis.com/css2?family=Rozha+One&family=Yatra+One&family=Modak&family=Tiro+Devanagari+Hindi:ital@0;1&family=Eczar:wght@400;500;600;700&family=Poppins:wght@400;500;600;700&display=swap');"}
</style>
<style>
${css}
</style>
${bodyInner}
<script>
${js}
</script>
`);
