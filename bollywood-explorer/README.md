# पर्दा · Parda — A Century of Hindi Cinema

A love letter to Bollywood: explore the **top-earning and top-IMDb-rated Hindi films of every
year since 1913** — 850 films across 11 eras — with real posters, cast photos, trivia (kisse),
songs, behind-the-scenes videos and interviews.

## Running it

It's a fully static site — no build step, no dependencies:

```bash
cd bollywood-explorer
python3 -m http.server 8000
# open http://localhost:8000
```

Or publish the `bollywood-explorer/` folder to GitHub Pages / Netlify / any static host.

## What's inside

- **A coffee-table book, not a database** — the site reads as chapters (one per era), each a
  sequence of editorial *year spreads*: the film of the year presented large with a pull-quote
  kissa and a rubber-stamp verdict, the rest of the marquee on a sprocketed filmstrip, and
  famous dialogue/song "ephemera" cards taped between the pages. Intermission plates turn you
  to the next chapter.
- **Printed-in-India aesthetic** — cream book paper with bandhani-dot texture and grain,
  sindoor red, marigold, turmeric, peacock, rani pink and gold; toran scallop borders,
  sunburst hoarding cover with offset-shadow Devanagari lettering (Modak/Yatra One), Rozha One
  editorial headlines, Eczar body text. Every chapter is printed on its own tinted paper, and
  old chapters get old-photo poster filters.
- **Two lists per year** — bookmark tabs flip between *₹ The Queue Outside* (earnings, curated
  from period trade reports; older decades are best historical estimates) and *★ The Critics'
  Shelf* (IMDb community ratings, approximate snapshots).
- **Film pages** — Hindi + English titles, director/cast/composer, verdict badges, curated
  trivia, song pills, and one-tap links to Spotify, Apple Music, JioSaavn, IMDb and Wikipedia.
- **Live imagery** — posters and cast portraits load at runtime from the Wikipedia/Wikimedia
  API (batched, redirect-aware, cached in `localStorage`), so the site ships no image assets
  and shows era-styled fallback cards when an image isn't available.
- **Videos** — click-to-load YouTube players (search-list embeds) for songs/jukeboxes,
  making-of footage and cast/director interviews, without hardcoding video IDs that rot.
- **Three editions of the book, not one stretched layout** — laptop is the full folio with
  alternating left/right facing-page spreads; iPad is the coffee-table edition in a generous
  single column; mobile is the pocket paperback with a bottom tab bar and full-screen pages.
- **Index & Matinee** — a book-style index for search, and a "Matinee" page that lets the
  book fall open on a random gem.

## Structure

```
index.html          app shell
css/base.css        design system (aged paper, gold leaf, film grain)
css/eras.css        per-decade palettes
css/devices.css     laptop / iPad / mobile designs
js/wiki.js          batched Wikipedia image loader with caching
js/app.js           hash router + views
data/eras.js        era metadata & registries
data/films-*.js     ~850 curated films, ~10 per year, with trivia & songs
```

## Data honesty

Box-office rankings before the 1990s come from trade lore and historical reports and are
estimates; IMDb ratings are approximate snapshots and drift over time. Posters and photos
belong to their rightful owners and are hot-loaded from Wikipedia. Corrections welcome —
each film entry is a small self-describing object in `data/films-<decade>.js`.
