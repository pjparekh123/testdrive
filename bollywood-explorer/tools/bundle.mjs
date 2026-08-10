#!/usr/bin/env node
/* ═══════════════════════════════════════════════════════════════════
   Bundle Parda into one self-contained HTML file.
   ─────────────────────────────────────────────────────────────────
   Inlines every stylesheet, script and data file so the book can be
   opened from a single file — handy for previews, email, or hosts
   that block external requests.

     node tools/bundle.mjs [fonts-inline.css] > parda.html

   Pass a stylesheet of @font-face rules with base64 data: URIs to
   embed the typefaces too; otherwise the Google Fonts link is kept.
   ═══════════════════════════════════════════════════════════════════ */

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const fontCssPath = process.argv[2];

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
const js = jsFiles.map((f) => `/* ${f} */\n${read(f)}`).join("\n;\n");

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
