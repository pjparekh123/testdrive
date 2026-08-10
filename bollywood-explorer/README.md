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

- **Era-first navigation** — each decade is its own themed world (palette, tone, filters):
  sepia for the silent era, silver-nitrate gold for the 1950s, disco magenta for the 1980s,
  streaming-dark teal for the 2020s. The whole app retints as you travel through time.
- **Two lists per year** — toggle between *₹ Box-Office Toppers* (curated from period trade
  reports; older decades are best historical estimates) and *★ IMDb Favourites* (community
  ratings, approximate snapshots).
- **Film pages** — Hindi + English titles, director/cast/composer, verdict badges, curated
  trivia, song pills, and one-tap links to Spotify, Apple Music, JioSaavn, IMDb and Wikipedia.
- **Live imagery** — posters and cast portraits load at runtime from the Wikipedia/Wikimedia
  API (batched, redirect-aware, cached in `localStorage`), so the site ships no image assets
  and shows era-styled fallback cards when an image isn't available.
- **Videos** — click-to-load YouTube players (search-list embeds) for songs/jukeboxes,
  making-of footage and cast/director interviews, without hardcoding video IDs that rot.
- **Three deliberate designs, not one stretched layout** — laptop is a cinema-lobby poster
  wall with hover reveals and a premiere-card dialog; iPad is a coffee-table album with a
  full-bleed sheet; mobile is a pocket app with a bottom tab bar, thumb-reach year chips and
  full-screen film pages.
- **Search & Kismat** — full-text search across films, people and composers; a "Kismat"
  wheel that surfaces a random gem worth discovering.

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
