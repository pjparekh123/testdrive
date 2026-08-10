# पर्दा · Parda — A Century of Hindi Cinema

A love letter to Bollywood: explore the **top-earning and top-IMDb-rated Hindi films of every
year since 1913** — 850 films across 11 eras — with real posters, cast photos, trivia (kisse),
songs, behind-the-scenes videos and interviews.

## Running it

It's a fully static site — no build step, no dependencies:

```bash
cd bollywood-explorer
node tools/fetch-posters.mjs     # once: bake in the real posters (needs network)
python3 -m http.server 8000      # open http://localhost:8000
```

Skip the first line and posters still resolve live from the Wikipedia API; bake
them in and they load instantly with no API call at all. Either way, any film
whose image can't be reached gets a painted poster plate instead of a gap.

Publish the `bollywood-explorer/` folder to GitHub Pages / Netlify / any static host.

### One self-contained file

```bash
node tools/bundle.mjs > parda.html                     # everything inlined
node tools/bundle.mjs fonts.css --embed-images > x.html # …plus the posters themselves
```

`--embed-images` inlines every baked poster as a `data:` URI, so the page shows
real photographs while making **zero** external requests — the only way to get
posters onto a host that blocks outside traffic (a strict CSP, an offline
laptop, an email attachment). Pass a stylesheet of `@font-face` rules with
base64 `src`s as the first argument to embed the typefaces too.

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
- **Real posters, baked in** — run `node tools/fetch-posters.mjs` once with network access and
  every film's real Wikipedia poster URL is written into `data/posters.js`. After that the site
  needs no API at runtime: posters appear instantly and keep working from `file://`, offline
  hosts and behind strict CSPs. Without that step the loader still resolves posters live from
  the Wikipedia API, and any film it can't reach gets a **painted poster plate** — generated
  hoarding-style art in one of eight saturated palettes, with the title, stars and director set
  in display type. Cast portraits fall back to gold-ringed monogram medallions the same way.
- **Videos** — click-to-load YouTube players (search-list embeds) for songs/jukeboxes,
  making-of footage and cast/director interviews, without hardcoding video IDs that rot.
- **Three editions of the book, not one stretched layout** — laptop is the full folio with
  alternating left/right facing-page spreads; iPad is the coffee-table edition in a generous
  single column; mobile is the pocket paperback with a bottom tab bar and full-screen pages.
- **Index & Matinee** — a book-style index for search, and a "Matinee" page that lets the
  book fall open on a random gem.

## Structure

```
index.html               app shell
css/base.css             design system — silk & paper, SVG ornament library,
                         jharokha niches, painted poster plates
css/eras.css             per-chapter paper, ink and silk
css/devices.css          laptop / iPad / mobile editions
js/posters.js            image resolver: baked URLs → Special:FilePath →
                         pageimages API → REST summary → painted plate
js/app.js                hash router + views
data/eras.js             era metadata & registries
data/ephemera.js         famous dialogues and song lines
data/posters.js          generated: real poster URLs keyed "year|title"
data/films-*.js          850 curated films, ~10 per year, with trivia & songs
tools/fetch-posters.mjs  resolves and bakes the poster URLs
```

## Before you publish

Check what will actually load:

```bash
node tools/fetch-posters.mjs          # bake
node tools/fetch-posters.mjs --audit  # coverage per decade + any dead URLs
```

Two things to know when the site is public:

- **Coverage is uneven.** Every film here has a Wikipedia article title in its
  record, but not every article carries a poster — expect near-complete coverage
  from the 1950s on and real gaps in the silent and studio eras. Those films show
  a painted plate, which is a designed state, not a broken one. `--audit` gives
  you the exact numbers.
- **The posters are other people's property.** Most Bollywood posters on Wikipedia
  are non-free files used there under a fair-use rationale that covers Wikipedia,
  not third-party sites. Hotlinking them from a public site is a copyright
  question worth settling for yourself — the painted plates are the safe default,
  and skipping the baking step keeps the site entirely free of hosted artwork.

Songs and videos open a YouTube search in a new tab rather than embedding a
player: embedding a *search* needed the `listType=search` parameter YouTube
retired, and pinning a video id per film is not something this data carries.

## Data honesty

Box-office rankings before the 1990s come from trade lore and historical reports and are
estimates; IMDb ratings are approximate snapshots and drift over time. Posters and photos
belong to their rightful owners and are hot-loaded from Wikipedia. Corrections welcome —
each film entry is a small self-describing object in `data/films-<decade>.js`.
