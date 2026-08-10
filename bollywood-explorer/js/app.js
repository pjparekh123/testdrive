/* ═══════════════════════════════════════════════════════════════════
   PARDA · app.js — a book you leaf through, not a database you query.
   Routes:  #/  #/era/:id  #/year/:y  #/film/:y/:slug
            #/timeline  #/search  #/surprise
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  const stage = document.getElementById("stage");
  const body = document.body;
  const layer = document.getElementById("film-layer");
  const sheet = document.getElementById("film-sheet");

  const ERAS = window.ERAS;
  const FILMS = window.FILMS;
  const EPHEMERA = window.EPHEMERA || [];
  const YEAR_NOTES = window.YEAR_NOTES || {};
  const YEARS = Object.keys(FILMS).map(Number).sort((a, b) => a - b);
  const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const DEVA_DIGITS = ["०", "१", "२", "३", "४", "५", "६", "७", "८", "९"];
  const deva = (n) => String(n).split("").map((d) => DEVA_DIGITS[+d] ?? d).join("");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const eraOf = (y) => ERAS.find((e) => y >= e.from && y <= e.to) || ERAS[ERAS.length - 1];
  const filmsOf = (y) => FILMS[y] || [];
  const byBO = (list) => list.slice().sort((a, b) => (a.f.er || 99) - (b.f.er || 99));
  const byIMDb = (list) => list.slice().sort((a, b) => (b.f.r || 0) - (a.f.r || 0));
  const indexed = (y) => filmsOf(y).map((f, i) => ({ f, i }));
  const yt = (q) => "https://www.youtube.com/results?search_query=" + encodeURIComponent(q);
  const ytEmbed = (q) => "https://www.youtube.com/embed?listType=search&list=" + encodeURIComponent(q);

  let totalFilms = 0;
  for (const y of YEARS) totalFilms += FILMS[y].length;

  function setEra(id) { body.dataset.era = id; }
  function setNav(name) {
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  }
  function render(html, eraId, nav) {
    closeSheet();
    setEra(eraId || "home");
    setNav(nav || "");
    stage.innerHTML = html;
    stage.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
    hydratePosters(stage);
  }

  /* ── poster hydration ─────────────────────────────────────── */
  function hydratePosters(scope) {
    scope.querySelectorAll("img[data-poster]").forEach((img) => {
      const [y, i] = img.dataset.poster.split(":");
      const f = filmsOf(Number(y))[Number(i)];
      if (f) window.Wiki.poster(f, img, Number(img.dataset.size || 480));
    });
  }

  /* ── shared fragments ─────────────────────────────────────── */
  /* A painted poster plate, drawn in CSS, for any film whose real
     poster can't be reached. Palette is picked from the title so a
     wall of them looks like a hand-painted hoarding, not a grid. */
  function hashOf(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h;
  }
  function fallbackHTML(f, y, cls) {
    const pal = hashOf(f.t + y) % 8;
    const stars = (f.c || []).slice(0, 3).join(" · ");
    const long = f.t.length > 22;
    return `<div class="poster-plate ${cls || ""}" data-fallback data-pal="${pal}">
      <span class="pp-rays" aria-hidden="true"></span>
      <span class="pp-inner">
        ${stars ? `<span class="pp-stars">${esc(stars)}</span>` : `<span class="pp-stars">${esc(String(y))}</span>`}
        <span class="pp-title${long ? " long" : ""}">${esc(f.t)}</span>
        ${f.h ? `<span class="pp-hi">${esc(f.h)}</span>` : ""}
        <span class="pp-rule" aria-hidden="true"></span>
        ${f.d ? `<span class="pp-dir">A ${esc(f.d.split(",")[0])} Film</span>` : ""}
      </span>
      <span class="pp-year">${deva(y)}</span>
    </div>`;
  }

  function heroHTML(f, y, i, opts) {
    opts = opts || {};
    const first = (f.tr && f.tr[0]) || "";
    const href = `#/film/${y}/${slug(f.t)}`;
    const rankLine = opts.rankLine || (f.er === 1 ? "The film of the year · Box-office no. 1" : (f.er ? `Box-office no. ${f.er}` : "The year's most loved"));
    return `
    <div class="hero-film ${opts.flip ? "flip" : ""}">
      <a class="mehrab hero-niche" href="${href}" aria-label="${esc(f.t)}">
        <div class="hero-poster">
          ${fallbackHTML(f, y)}
          <img alt="Poster of ${esc(f.t)}" loading="lazy" data-poster="${y}:${i}" data-size="640" style="position:absolute;inset:0">
        </div>
        <div class="niche-caption">${deva(y)} · now showing</div>
      </a>
      <div class="hero-info">
        <span class="hero-rank">${esc(rankLine)}</span>
        <a class="hero-title" href="${href}">${esc(f.t)}</a>
        ${f.h ? `<span class="hero-hi">${esc(f.h)}</span>` : ""}
        <p class="hero-credits">${f.d ? `<b>${esc(f.d)}</b>` : ""}${f.c && f.c.length ? ` · ${esc(f.c.slice(0, 4).join(", "))}` : ""}${f.m ? ` · <b>♪</b> ${esc(f.m)}` : ""}</p>
        <div class="hero-badges">
          ${f.r ? `<span class="b-imdb">★ ${f.r.toFixed(1)}</span>` : ""}
          ${f.v ? `<span class="stamp">${esc(f.v)}</span>` : ""}
        </div>
        ${first ? `<p class="pullquote hero-quote">${esc(first)}</p>` : ""}
        <a class="hero-more" href="${href}">Open the kissa file →</a>
      </div>
    </div>`;
  }

  function frameHTML(f, y, i, badge) {
    return `
    <a class="frame" href="#/film/${y}/${slug(f.t)}" aria-label="${esc(f.t)}">
      <div class="fr-poster">
        ${badge || ""}
        ${fallbackHTML(f, y)}
        <img alt="" loading="lazy" data-poster="${y}:${i}" data-size="240" style="position:absolute;inset:0">
      </div>
      <span class="fr-cap"><b>${esc(f.t)}</b>${f.d ? esc(f.d) : ""}</span>
    </a>`;
  }

  function spreadHTML(y, opts) {
    opts = opts || {};
    const e = eraOf(y);
    const list = byBO(indexed(y));
    if (!list.length) return "";
    const hero = list[0];
    const rest = list.slice(1);
    const note = YEAR_NOTES[y];
    return `
    <section class="spread" id="y${y}">
      <div class="spread-mast">
        <h2 class="spread-year">
          <a href="#/year/${y}" title="Open ${y} as a full page">${y}</a>
          <span class="deva-year">${deva(y)}</span>
        </h2>
        ${note ? `<p class="spread-note">${esc(note)}</p>` : ""}
      </div>
      ${heroHTML(hero.f, y, hero.i, { flip: opts.flip })}
      ${rest.length ? `
      <div class="strip-label">Also on the marquee, ${y} — <a href="#/year/${y}" style="letter-spacing:.1em">open the full page ›</a></div>
      <div class="filmstrip">${rest.map(({ f, i }) =>
        frameHTML(f, y, i, f.er ? `<span class="fr-rank">${f.er}</span>` : "")).join("")}</div>` : ""}
    </section>`;
  }

  function interludeHTML(item) {
    if (!item) return "";
    const linked = findFilm(item.film, item.y);
    const src = `${item.film} · ${item.y}`;
    const inner = `
      <span class="in-kind">${item.kind === "song" ? "नग़मा · a song remembered" : "डायलॉग · a line remembered"}</span>
      <p class="in-q">${esc(item.q)}</p>
      ${item.hi ? `<p class="in-hi">${esc(item.hi)}</p>` : ""}
      <p class="in-src">from <b>${esc(src)}</b></p>`;
    return linked
      ? `<a class="interlude" href="#/film/${item.y}/${slug(linked.t)}">${inner}</a>`
      : `<div class="interlude">${inner}</div>`;
  }

  function findFilm(title, y) {
    const list = filmsOf(y);
    return list.find((f) => slug(f.t) === slug(title)) || null;
  }

  /* ── the cover (home) ─────────────────────────────────────── */
  function viewHome() {
    const plates = ERAS.map((e, idx) => {
      const years = YEARS.filter((y) => y >= e.from && y <= e.to);
      // three landmark films, spread across the chapter, shown as a fan
      const step = Math.max(1, Math.floor(years.length / 3));
      const picks = [];
      for (let n = 0; n < years.length && picks.length < 3; n += step) {
        const y = years[n];
        const top = byBO(indexed(y))[0];
        if (top) picks.push({ f: top.f, y, i: top.i });
      }
      const fan = picks.map((p, n) => `
        <span class="cp-card" style="--n:${n - 1}">
          ${fallbackHTML(p.f, p.y)}
          <img alt="" loading="lazy" data-poster="${p.y}:${p.i}" data-size="240" style="position:absolute;inset:0">
        </span>`).join("");
      return `
      <a class="chapter-plate fade-in" data-era="${e.id}" href="#/era/${e.id}">
        <span class="cp-spine" aria-hidden="true"></span>
        <span class="cp-body">
          <span class="cp-roman">Chapter ${ROMAN[idx]} · ${e.from}–${e.to} · ${deva(e.from)}–${deva(e.to)}</span>
          <span class="cp-name">${esc(e.en)}<span class="hi">${esc(e.hi)}</span></span>
          <span class="cp-tag">${esc(e.tag)}</span>
          <span class="cp-films">Featuring ${picks.map((p) => `<b>${esc(p.f.t)}</b>`).join(" · ")}</span>
          <span class="cp-go">Turn to this chapter →</span>
        </span>
        <span class="cp-fan" aria-hidden="true">${fan}</span>
      </a>`;
    }).join("");
    render(`
      <section class="cover fade-in">
        <p class="cover-kicker">किस्से · नग़मे · सितारे</p>
        <h1 class="cover-title">सौ साल का सिनेमा</h1>
        <p class="cover-en">A Hundred Years of Hindi Cinema</p>
        <p class="cover-deck">A coffee-table book of the movies India stood in line for — the biggest
        hits and best-loved films of every single year since 1913, with their posters, faces,
        songs, and the kisse told about them ever since.</p>
        <div class="cover-ctas">
          <a class="btn-marquee" href="#/era/silent">Begin at the beginning · 1913 →</a>
          <a class="btn-marquee ghost" href="#/surprise">Open a page at random ✦</a>
        </div>
        <div class="cover-strip">
          <div class="cs-cell"><b>${YEARS[YEARS.length - 1] - YEARS[0] + 1}</b><span>years</span></div>
          <div class="cs-cell"><b>${totalFilms}</b><span>films</span></div>
          <div class="cs-cell"><b>${ERAS.length}</b><span>chapters</span></div>
        </div>
      </section>
      <div class="paisley-div"></div>
      <section class="toc-head fade-in">
        <h2>The Chapters <span class="hi">अध्याय</span></h2>
      </section>
      <section class="toc stagger">${plates}</section>
    `, "home", "home");
  }

  /* ── a chapter (era page) ─────────────────────────────────── */
  function viewEra(id) {
    const idx = ERAS.findIndex((x) => x.id === id);
    if (idx < 0) return viewHome();
    const e = ERAS[idx];
    const years = YEARS.filter((y) => y >= e.from && y <= e.to);
    const eph = EPHEMERA.filter((x) => x.y >= e.from && x.y <= e.to);
    let ephUsed = 0;
    const spreads = years.map((y, i) => {
      let out = spreadHTML(y, { flip: i % 2 === 1 });
      if ((i + 1) % 3 === 0 && ephUsed < eph.length) {
        out += interludeHTML(eph[ephUsed++]);
      }
      return out;
    }).join("");
    const next = ERAS[idx + 1];
    render(`
      <header class="chapter-cover fade-in">
        <div class="mehrab chapter-niche">
          <p class="cc-roman">Chapter ${ROMAN[idx]}</p>
          <h1>${esc(e.en)}<span class="hi-big">${esc(e.hi)}</span></h1>
          <p class="cc-years">${e.from} — ${e.to} · ${deva(e.from)} — ${deva(e.to)}</p>
        </div>
        <p class="essay drop">${esc(e.blurb)}</p>
        ${e.note ? `<p class="note">${esc(e.note)}</p>` : ""}
        <div class="paisley-div small"></div>
      </header>
      ${spreads}
      ${next ? `
      <a class="chapter-next" href="#/era/${next.id}">
        <span class="cn-inter">मध्यांतर · Intermission</span>
        <span class="cn-label">when you're ready, turn to Chapter ${ROMAN[idx + 1]}</span>
        <span class="cn-name">${esc(next.en)} · ${esc(next.hi)} →</span>
      </a>` : `
      <div class="chapter-next" style="cursor:default">
        <span class="cn-inter">समाप्त · The End</span>
        <span class="cn-label">— of the book so far. The movies, thankfully, continue. —</span>
      </div>`}
    `, e.id, "timeline");
  }

  /* ── a single year page ───────────────────────────────────── */
  function viewYear(y, mode) {
    y = Number(y);
    if (!FILMS[y]) {
      y = YEARS.reduce((best, c) => Math.abs(c - y) < Math.abs(best - y) ? c : best, YEARS[0]);
    }
    const e = eraOf(y);
    mode = mode || "bo";
    const list = mode === "imdb" ? byIMDb(indexed(y)) : byBO(indexed(y));
    const hero = list[0];
    const rest = list.slice(1);
    const idx = YEARS.indexOf(y);
    const prev = YEARS[idx - 1], next = YEARS[idx + 1];
    const note = YEAR_NOTES[y];
    render(`
      <header class="year-mast fade-in">
        <p class="cc-roman"><a href="#/era/${e.id}">${e.motif} ${esc(e.en)} · ${esc(e.hi)}</a></p>
        <div class="year-big"><b>${y}</b><span class="deva-year">${deva(y)}</span></div>
        ${note ? `<p class="essay-line">${esc(note)}</p>` : ""}
        <div class="bookmarks" role="tablist">
          <button role="tab" aria-selected="${mode !== "imdb"}" class="${mode !== "imdb" ? "on" : ""}" data-mode="bo">₹ The Queue Outside</button>
          <button role="tab" aria-selected="${mode === "imdb"}" class="${mode === "imdb" ? "on" : ""}" data-mode="imdb">★ The Critics' Shelf</button>
        </div>
        <p class="list-note">${mode === "imdb"
          ? "Arranged by IMDb rating — the films that aged best."
          : "Arranged by earnings — the films India queued up for."}</p>
      </header>
      ${hero ? heroHTML(hero.f, y, hero.i, {
        rankLine: mode === "imdb" ? "The best-loved film of " + y : undefined,
      }) : ""}
      <div class="strip-label">The rest of ${y}'s marquee</div>
      <section class="poster-wall stagger">
        ${rest.map(({ f, i }, n) => `
        <a class="wall-card" href="#/film/${y}/${slug(f.t)}">
          <div class="wall-poster">
            <span class="wall-rank">${mode === "imdb" ? "★" + (f.r ? f.r.toFixed(1) : "–") : (f.er || "·")}</span>
            ${fallbackHTML(f, y)}
            <img alt="" loading="lazy" data-poster="${y}:${i}" data-size="480" style="position:absolute;inset:0">
          </div>
          <span class="wall-cap">
            <b>${esc(f.t)}</b>
            ${f.h ? `<span class="hi">${esc(f.h)}</span>` : ""}
            <span class="sub">${esc(f.d || "")}${f.m ? " · ♪ " + esc(f.m) : ""}</span>
          </span>
        </a>`).join("")}
      </section>
      <nav class="page-turn">
        ${prev ? `<a href="#/year/${prev}">⟵ turn back to ${prev}</a>` : "<span></span>"}
        <a href="#/era/${e.id}">⌂ chapter: ${esc(e.en)}</a>
        ${next ? `<a href="#/year/${next}">turn the page to ${next} ⟶</a>` : "<span></span>"}
      </nav>
    `, e.id, "timeline");
    stage.querySelectorAll(".bookmarks button").forEach((b) => {
      b.addEventListener("click", () => viewYear(y, b.dataset.mode));
    });
  }

  /* ── all chapters & years (timeline) ──────────────────────── */
  function viewTimeline() {
    const rows = ERAS.map((e, idx) => {
      const years = YEARS.filter((y) => y >= e.from && y <= e.to);
      return `
      <section class="toc-era fade-in" data-era="${e.id}">
        <h2 class="toc-era-head">
          <span class="toc-era-num">${ROMAN[idx]}</span>
          <a href="#/era/${e.id}">${esc(e.en)}</a>
          <span class="hi">${esc(e.hi)}</span>
          <span class="toc-dots"></span>
          <span class="toc-range">${e.from}–${e.to}</span>
        </h2>
        <div class="toc-years">
          ${years.map((y) => `<a class="year-tab" href="#/year/${y}"><b>${y}</b><span>${deva(y)}</span></a>`).join("")}
        </div>
      </section>`;
    }).join("");
    render(`
      <header class="chapter-cover fade-in">
        <div class="mehrab chapter-niche">
          <p class="cc-roman">The Book</p>
          <h1>Contents<span class="hi-big">अनुक्रमणिका</span></h1>
          <p class="cc-years">${YEARS.length} years · ${ERAS.length} chapters</p>
        </div>
        <p class="essay plain">Every chapter, every year — open the book anywhere.</p>
        <div class="paisley-div small"></div>
      </header>
      <div class="toc-list">${rows}</div>
    `, "home", "timeline");
  }

  /* ── the index (search) ───────────────────────────────────── */
  function viewSearch(q) {
    render(`
      <div class="search-wrap fade-in">
        <header class="search-head">
          <div class="mehrab chapter-niche" style="max-width:460px">
            <p class="cc-roman">Back of the book</p>
            <h1>The Index<span class="hi-big">तलाश</span></h1>
          </div>
        </header>
        <input id="search-input" type="search" autocomplete="off"
          placeholder="A film, a star, a music maker… try “Guru Dutt”" value="${esc(q || "")}">
        <p class="search-hint">${totalFilms} films, ${YEARS.length} years, one book</p>
        <div class="sr-list" id="sr-list"></div>
      </div>
    `, "home", "search");
    const input = document.getElementById("search-input");
    const list = document.getElementById("sr-list");
    function run() {
      const needle = input.value.trim().toLowerCase();
      if (needle.length < 2) { list.innerHTML = ""; return; }
      const hits = [];
      for (const y of YEARS) {
        FILMS[y].forEach((f) => {
          const hay = [f.t, f.h, f.d, f.m, (f.c || []).join(" ")].join(" ").toLowerCase();
          if (hay.includes(needle)) hits.push({ f, y });
        });
        if (hits.length > 60) break;
      }
      list.innerHTML = hits.slice(0, 60).map(({ f, y }) => `
        <a class="sr-item" href="#/film/${y}/${slug(f.t)}">
          <span class="sr-year">${y}</span><b>${esc(f.t)}</b>
          <span class="sr-meta">${esc(f.d || "")} · ${esc((f.c || []).slice(0, 3).join(", "))}</span>
        </a>`).join("") || `<p class="search-hint">Kuch nahi mila — try another spelling?</p>`;
    }
    input.addEventListener("input", run);
    input.focus();
    if (q) run();
  }

  /* ── matinee (surprise) ───────────────────────────────────── */
  function viewSurprise() {
    const pool = [];
    for (const y of YEARS) FILMS[y].forEach((f, i) => { if ((f.r || 0) >= 7.4 || (f.tr && f.tr.length > 1)) pool.push({ f, y, i }); });
    const pick = pool[Math.floor(Math.random() * pool.length)];
    const e = eraOf(pick.y);
    render(`
      <div class="matinee fade-in">
        <p class="cover-kicker">मैटिनी शो · today's matinee</p>
        <h1>House Full!</h1>
        <p class="deck">The book falls open on <b>${pick.y}</b> — ${esc(e.en)}. On the marquee:</p>
        <div class="matinee-stage">${heroPosterOnly(pick.f, pick.y, pick.i)}</div>
        <div>
          <a class="hero-title" style="font-size:1.6rem" href="#/film/${pick.y}/${slug(pick.f.t)}">${esc(pick.f.t)}</a>
          ${pick.f.h ? `<div class="hero-hi">${esc(pick.f.h)}</div>` : ""}
        </div>
        <a class="btn-marquee" href="#/film/${pick.y}/${slug(pick.f.t)}">Open the kissa file →</a>
        <button class="btn-marquee ghost" id="respin">Another show ✦</button>
      </div>
    `, e.id, "surprise");
    document.getElementById("respin").addEventListener("click", viewSurprise);
  }

  function heroPosterOnly(f, y, i) {
    return `
    <a class="mehrab hero-niche" href="#/film/${y}/${slug(f.t)}">
      <div class="hero-poster">
        ${fallbackHTML(f, y)}
        <img alt="Poster of ${esc(f.t)}" data-poster="${y}:${i}" data-size="640" style="position:absolute;inset:0">
      </div>
      <div class="niche-caption">${deva(y)} · now showing</div>
    </a>`;
  }

  /* ── film sheet — the kissa file ──────────────────────────── */
  function videoSlot(label, sub, query) {
    return `
    <div class="video-slot" data-q="${esc(query)}">
      <button class="vs-cover" aria-label="Play: ${esc(label)}">
        <span class="vs-play">▶</span>
        <span class="vs-label">${esc(label)}</span>
        <span class="vs-sub">${esc(sub)}</span>
      </button>
    </div>`;
  }

  function openFilm(y, filmSlug) {
    y = Number(y);
    const films = filmsOf(y);
    const fi = films.findIndex((x) => slug(x.t) === filmSlug);
    if (fi < 0) return viewYear(y);
    const f = films[fi];
    const e = eraOf(y);
    setEra(e.id);
    const lead = (f.c && f.c[0]) || "";
    const searchTerm = `${f.t} ${y}`;
    const wikiUrl = "https://en.wikipedia.org/wiki/" + encodeURIComponent((f.w || f.t).replace(/ /g, "_"));

    const castHTML = (f.c || []).map((name) => {
      const initials = name.replace(/\(.*?\)/g, "").trim().split(/\s+/)
        .map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
      return `
      <div class="cast-card">
        <div class="cast-ph" data-pal="${hashOf(name) % 8}">
          <span class="cast-mono" data-fallback aria-hidden="true">${esc(initials)}</span>
          <img alt="${esc(name)}" data-person="${esc(name)}">
        </div>
        <span class="cast-name">${esc(name)}</span>
      </div>`;
    }).join("");

    // the first kissa is quoted up top, so the list below starts at the second
    const triviaHTML = (f.tr || []).slice(1).map((t) => `<div class="trivia-item">${esc(t)}</div>`).join("");
    const songsHTML = (f.s || []).map((s) =>
      `<a class="song-pill" target="_blank" rel="noopener" href="${yt(`${s} ${f.t} ${y} song`)}">${esc(s)}</a>`).join("");

    const videos = [
      videoSlot(`Songs of ${f.t}`, "video jukebox · via YouTube search", `${searchTerm} full songs jukebox`),
      videoSlot("Behind the scenes", "making-of & rare footage", `${searchTerm} making behind the scenes rare`),
      videoSlot(`${f.d ? f.d.split(",")[0] : "Director"} & cast in conversation`, "interviews & retrospectives", `${f.t} ${f.d || ""} ${lead} interview`),
    ].join("");

    sheet.innerHTML = `
      <button class="fs-close" aria-label="Close">✕</button>
      <div class="fs-body">
        <div class="fs-cert">
          <span class="fc-top">पर्दा आर्काइव · The Parda Archive · Kissa File No. ${y}/${(fi + 1)}</span>
          <span class="fc-line">${esc(e.en)} · certified classic of ${y}</span>
        </div>
        <div class="fs-top">
          <div class="mehrab fs-niche">
            <div class="fs-poster">
              ${fallbackHTML(f, y)}
              <img alt="Poster of ${esc(f.t)}" data-fs-poster style="position:absolute;inset:0">
            </div>
            <div class="niche-caption">${deva(y)}</div>
          </div>
          <div class="fs-id">
            <span class="fs-kicker">${y} · ${esc(e.en)} · ${esc(e.hi)}</span>
            <h2 id="film-title">${esc(f.t)}</h2>
            ${f.h ? `<p class="fs-hi">${esc(f.h)}</p>` : ""}
            <div class="fs-facts">
              ${f.d ? `<span><b>Directed by</b> ${esc(f.d)}</span>` : ""}
              ${f.c && f.c.length ? `<span><b>Starring</b> ${esc(f.c.join(", "))}</span>` : ""}
              ${f.m ? `<span><b>Music</b> ${esc(f.m)}</span>` : ""}
            </div>
            <div class="fs-badges">
              ${f.r ? `<span class="b-imdb">★ ${f.r.toFixed(1)} IMDb</span>` : ""}
              ${f.er ? `<span class="b-gross">#${f.er} at the ${y} box office</span>` : ""}
              ${f.bo ? `<span class="b-gross">${esc(f.bo)}</span>` : ""}
              ${f.v ? `<span class="stamp teal">${esc(f.v)}</span>` : ""}
            </div>
            <div class="fs-links">
              <a class="lnk" target="_blank" rel="noopener" href="${wikiUrl}">📖 Wikipedia</a>
              <a class="lnk" target="_blank" rel="noopener" href="https://www.imdb.com/find/?q=${encodeURIComponent(searchTerm)}">⭐ IMDb</a>
              <a class="lnk spotify" target="_blank" rel="noopener" href="https://open.spotify.com/search/${encodeURIComponent(f.t + " " + (f.m || ""))}">🟢 Spotify</a>
              <a class="lnk apple" target="_blank" rel="noopener" href="https://music.apple.com/us/search?term=${encodeURIComponent(f.t + " " + y)}"> Apple Music</a>
              <a class="lnk yt" target="_blank" rel="noopener" href="https://www.jiosaavn.com/search/${encodeURIComponent(f.t)}">🎵 JioSaavn</a>
            </div>
            ${f.tr && f.tr[0] ? `<p class="pullquote fs-lead">${esc(f.tr[0])}</p>` : ""}
          </div>
        </div>

        ${f.c && f.c.length ? `
        <section class="fs-section">
          <h3>The Faces <span class="hi">सितारे</span></h3>
          <div class="cast-strip">${castHTML}</div>
        </section>` : ""}

        ${triviaHTML ? `
        <section class="fs-section">
          <h3>Kisse &amp; Trivia <span class="hi">क़िस्से</span></h3>
          <div class="trivia-list">${triviaHTML}</div>
        </section>` : ""}

        <section class="fs-section">
          <h3>The Projection Room <span class="hi">देखिए</span></h3>
          <div class="video-row">${videos}</div>
        </section>

        ${songsHTML ? `
        <section class="fs-section">
          <h3>On the Gramophone <span class="hi">नग़मे</span></h3>
          <div class="song-pills">${songsHTML}</div>
        </section>` : ""}

        <div class="paisley-div small"></div>
      </div>`;

    layer.hidden = false;
    body.style.overflow = "hidden";
    sheet.scrollTop = 0;

    window.Wiki.poster(f, sheet.querySelector("[data-fs-poster]"), 640);
    sheet.querySelectorAll("[data-person]").forEach((img) => window.Wiki.person(img.dataset.person, img));
    sheet.querySelector(".fs-close").addEventListener("click", () => history.back());
    sheet.querySelectorAll(".video-slot").forEach((slot) => {
      slot.querySelector(".vs-cover").addEventListener("click", () => {
        const q = slot.dataset.q;
        // Some hosts block YouTube iframes, so always offer the direct link.
        slot.innerHTML =
          `<iframe src="${ytEmbed(q)}" title="YouTube results" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
           <a class="vs-out" target="_blank" rel="noopener" href="${yt(q)}">Watch on YouTube ↗</a>`;
      });
    });
    sheet.querySelector(".fs-close").focus({ preventScroll: true });
  }

  function closeSheet() {
    if (layer.hidden) return;
    layer.hidden = true;
    body.style.overflow = "";
    sheet.innerHTML = "";
  }

  document.getElementById("film-scrim").addEventListener("click", () => history.back());
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !layer.hidden) history.back();
  });
  document.getElementById("search-toggle").addEventListener("click", () => { location.hash = "#/search"; });

  /* ── router ───────────────────────────────────────────────── */
  function route() {
    const h = location.hash || "#/";
    const parts = h.replace(/^#\//, "").split("/").filter(Boolean);
    const view = parts[0] || "";
    if (view !== "film") closeSheet();
    switch (view) {
      case "": viewHome(); break;
      case "era": viewEra(parts[1]); break;
      case "year": viewYear(parts[1]); break;
      case "timeline": viewTimeline(); break;
      case "search": viewSearch(decodeURIComponent(parts[1] || "")); break;
      case "surprise": viewSurprise(); break;
      case "film": {
        if (!stage.querySelector(".spread") && !stage.querySelector(".poster-wall")) {
          viewYear(parts[1]);
        }
        openFilm(parts[1], parts[2]);
        break;
      }
      default: viewHome();
    }
  }

  window.addEventListener("hashchange", route);
  route();
})();
