/* ═══════════════════════════════════════════════════════════════════
   PARDA · app.js — hash-routed single-page explorer.
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
  const YEAR_NOTES = window.YEAR_NOTES || {};
  const YEARS = Object.keys(FILMS).map(Number).sort((a, b) => a - b);

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const eraOf = (y) => ERAS.find((e) => y >= e.from && y <= e.to) || ERAS[ERAS.length - 1];
  const filmsOf = (y) => FILMS[y] || [];
  const yt = (q) => "https://www.youtube.com/results?search_query=" + encodeURIComponent(q);
  const ytEmbed = (q) => "https://www.youtube.com/embed?listType=search&list=" + encodeURIComponent(q);

  let totalFilms = 0;
  for (const y of YEARS) totalFilms += FILMS[y].length;

  function setEra(id) { body.dataset.era = id; }
  function setNav(name) {
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  }
  function render(html, eraId, nav) {
    closeSheet(true);
    setEra(eraId || "home");
    setNav(nav || "");
    stage.innerHTML = html;
    stage.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  /* ── shared renderers ─────────────────────────────────────── */

  function ticketHTML(y, sub) {
    return `<a class="ticket" href="#/year/${y}"><b>${y}</b><span>${esc(sub || "admit one")}</span></a>`;
  }

  function filmCardHTML(f, y, i, mode) {
    const medal = mode === "imdb"
      ? `<span class="rank-medal imdb" title="IMDb rating">★${f.r ? f.r.toFixed(1) : "–"}</span>`
      : (f.er ? `<span class="rank-medal" title="No. ${f.er} at the box office">${f.er}</span>` : "");
    const badges = [
      f.r ? `<span class="b-imdb">★ ${f.r.toFixed(1)}</span>` : "",
      f.er ? `<span class="b-gross">#${f.er} grosser</span>` : "",
      f.v ? `<span class="b-verdict">${esc(f.v)}</span>` : "",
    ].join("");
    const hover = f.tr && f.tr.length ? `<div class="fc-hover">“${esc(f.tr[0])}”</div>` : "";
    return `
    <a class="film-card" href="#/film/${y}/${slug(f.t)}" aria-label="${esc(f.t)} (${y})">
      <div class="poster-wrap">
        ${medal}
        <div class="poster-fallback">
          <span class="pf-orn">❋</span>
          <span class="pf-title">${esc(f.t)}</span>
          <span class="pf-year">${y}</span>
        </div>
        <img alt="" loading="lazy" data-poster="${y}:${i}">
        ${hover}
      </div>
      <div class="fc-meta">
        <span class="fc-title">${esc(f.t)}</span>
        ${f.h ? `<span class="fc-hi">${esc(f.h)}</span>` : ""}
        <span class="fc-sub">${esc(f.d || "")}${f.m ? " · ♪ " + esc(f.m) : ""}</span>
        <span class="fc-badges">${badges}</span>
      </div>
    </a>`;
  }

  function hydratePosters(scope) {
    scope.querySelectorAll("img[data-poster]").forEach((img) => {
      const [y, i] = img.dataset.poster.split(":");
      const f = filmsOf(Number(y))[Number(i)];
      if (f) window.Wiki.poster(f, img, 480);
    });
  }

  /* ── views ────────────────────────────────────────────────── */

  function viewHome() {
    const cards = ERAS.map((e) => `
      <a class="era-card fade-in" data-era="${e.id}" data-motif="${e.motif}" href="#/era/${e.id}">
        <span class="era-years">${e.from} — ${e.to}</span>
        <span class="era-name">${esc(e.en)}<span class="hi">${esc(e.hi)}</span></span>
        <span class="era-tag2">${esc(e.tag)}</span>
        <span class="era-blurb">${esc(e.blurb)}</span>
        <span class="era-go">Enter the era →</span>
      </a>`).join("");
    render(`
      <section class="hero fade-in">
        <p class="hero-pre">बॉक्स ऑफिस · Box Office &nbsp;✦&nbsp; IMDb</p>
        <h1 class="hero-hi">सौ साल का सिनेमा</h1>
        <p class="hero-en">A Hundred Years of Hindi Cinema</p>
        <p class="hero-sub">From Phalke's silent gods to Pathaan's roar — the top-earning and best-loved
        films of every single year, with the posters, faces, songs and kisse that made them immortal.</p>
        <div class="hero-stats">
          <div class="hero-stat"><b>${YEARS[YEARS.length - 1] - YEARS[0] + 1}</b><span>years</span></div>
          <div class="hero-stat"><b>${totalFilms}</b><span>films</span></div>
          <div class="hero-stat"><b>${ERAS.length}</b><span>eras</span></div>
        </div>
        <p class="orn">✦ ❋ ✦</p>
      </section>
      <section class="era-list stagger">${cards}</section>
    `, "home", "home");
  }

  function viewEra(id) {
    const e = ERAS.find((x) => x.id === id);
    if (!e) return viewHome();
    const years = YEARS.filter((y) => y >= e.from && y <= e.to);
    const tickets = years.map((y) => {
      const top = filmsOf(y).slice().sort((a, b) => (a.er || 99) - (b.er || 99))[0];
      return ticketHTML(y, top ? top.t : "");
    }).join("");
    render(`
      <header class="era-head fade-in">
        <span class="era-years">${e.from} — ${e.to} &nbsp;${e.motif}</span>
        <h1>${esc(e.en)}<span class="hi-big">${esc(e.hi)}</span></h1>
        <p>${esc(e.blurb)}</p>
        ${e.note ? `<p class="era-note">${esc(e.note)}</p>` : ""}
      </header>
      <div class="rule-orn">❋ pick a year, tear the ticket ❋</div>
      <nav class="ticket-strip stagger" aria-label="Years in this era">${tickets}</nav>
    `, e.id, "home");
  }

  function viewYear(y, mode) {
    y = Number(y);
    if (!FILMS[y]) {
      const nearest = YEARS.reduce((best, c) => Math.abs(c - y) < Math.abs(best - y) ? c : best, YEARS[0]);
      y = nearest;
    }
    const e = eraOf(y);
    mode = mode || "bo";
    const films = filmsOf(y).map((f, i) => ({ f, i }));
    const sorted = mode === "imdb"
      ? films.slice().sort((a, b) => (b.f.r || 0) - (a.f.r || 0))
      : films.slice().sort((a, b) => (a.f.er || 99) - (b.f.er || 99));
    const idx = YEARS.indexOf(y);
    const prev = YEARS[idx - 1], next = YEARS[idx + 1];
    const note = YEAR_NOTES[y];
    const eraYears = YEARS.filter((yy) => yy >= e.from && yy <= e.to);
    render(`
      <header class="year-head fade-in">
        <a class="year-era-link" href="#/era/${e.id}">${e.motif} ${esc(e.en)} · ${esc(e.hi)}</a>
        <div class="year-nav">
          ${prev ? `<a class="yr-btn" href="#/year/${prev}">← ${prev}</a>` : "<span></span>"}
          <h1 class="year-big">${y}</h1>
          ${next ? `<a class="yr-btn" href="#/year/${next}">${next} →</a>` : "<span></span>"}
        </div>
        ${note ? `<p class="year-context">${esc(note)}</p>` : ""}
        <div class="list-toggle" role="tablist">
          <button role="tab" aria-selected="${mode !== "imdb"}" class="${mode !== "imdb" ? "on" : ""}" data-mode="bo">₹ Box-Office Toppers</button>
          <button role="tab" aria-selected="${mode === "imdb"}" class="${mode === "imdb" ? "on" : ""}" data-mode="imdb">★ IMDb Favourites</button>
        </div>
        <p class="list-note">${mode === "imdb"
          ? "Ranked by IMDb community rating — the films that aged best."
          : "Ranked by earnings that year — the films India queued up for."}</p>
      </header>
      <nav class="ticket-strip" aria-label="Years nearby">
        ${eraYears.map((yy) => yy === y
          ? `<span class="ticket" style="border-color:var(--era-a)"><b style="color:var(--era-a)">${yy}</b><span>now showing</span></span>`
          : ticketHTML(yy)).join("")}
      </nav>
      <section class="film-grid stagger">
        ${sorted.map(({ f, i }) => filmCardHTML(f, y, i, mode)).join("")}
      </section>
    `, e.id, "home");
    stage.querySelectorAll(".list-toggle button").forEach((b) => {
      b.addEventListener("click", () => viewYear(y, b.dataset.mode));
    });
    hydratePosters(stage);
    const strip = stage.querySelector(".ticket-strip");
    const current = strip && strip.querySelector('span.ticket');
    if (current && strip.scrollWidth > strip.clientWidth) {
      strip.scrollLeft = current.offsetLeft - strip.clientWidth / 2 + current.offsetWidth / 2;
    }
  }

  function viewTimeline() {
    const rows = ERAS.map((e) => {
      const years = YEARS.filter((y) => y >= e.from && y <= e.to);
      return `
      <section class="tl-era fade-in" >
        <h2 class="tl-era-name"><a href="#/era/${e.id}">${e.motif} ${esc(e.en)}</a><span class="hi">${esc(e.hi)}</span></h2>
        <div class="tl-years">${years.map((y) => ticketHTML(y)).join("")}</div>
      </section>`;
    }).join("");
    render(`
      <header class="era-head fade-in">
        <h1>Every Year<span class="hi-big">हर साल की कहानी</span></h1>
        <p>One ticket per year — pick any and see what India was watching.</p>
      </header>
      <div class="tl-wrap">${rows}</div>
    `, "home", "timeline");
  }

  function viewSearch(q) {
    render(`
      <div class="search-wrap fade-in">
        <header class="era-head" style="padding-top:.5rem">
          <h1>Talaash<span class="hi-big">तलाश</span></h1>
        </header>
        <input id="search-input" type="search" autocomplete="off"
          placeholder="A film, a star, a director, a music maker… try “Guru Dutt”" value="${esc(q || "")}">
        <p class="search-hint">Searching ${totalFilms} films across ${YEARS.length} years</p>
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

  function viewSurprise() {
    const pool = [];
    for (const y of YEARS) FILMS[y].forEach((f) => { if ((f.r || 0) >= 7.4 || (f.tr && f.tr.length > 1)) pool.push({ f, y }); });
    const pick = pool[Math.floor(Math.random() * pool.length)];
    render(`
      <div class="surprise-frame fade-in">
        <p class="hero-pre">आज की किस्मत · today's fate</p>
        <h1 class="hero-hi" style="font-size:clamp(2.2rem,6vw,3.6rem)">Kismat Konnection</h1>
        <p class="hero-sub">The reel of fortune has landed on a gem from <b>${pick.y}</b> —</p>
        <div class="film-grid" style="max-width:280px;width:100%">${filmCardHTML(pick.f, pick.y, filmsOf(pick.y).indexOf(pick.f), "bo")}</div>
        <button class="btn-gold" id="respin">Spin again ✦</button>
      </div>
    `, eraOf(pick.y).id, "surprise");
    hydratePosters(stage);
    document.getElementById("respin").addEventListener("click", viewSurprise);
  }

  /* ── film sheet ───────────────────────────────────────────── */

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
    const f = films.find((x) => slug(x.t) === filmSlug);
    if (!f) return viewYear(y);
    const e = eraOf(y);
    setEra(e.id);
    const lead = (f.c && f.c[0]) || "";
    const searchTerm = `${f.t} ${y}`;
    const wikiUrl = "https://en.wikipedia.org/wiki/" + encodeURIComponent((f.w || f.t).replace(/ /g, "_"));

    const castHTML = (f.c || []).map((name) => `
      <div class="cast-card">
        <div class="cast-ph"><span aria-hidden="true">❋</span><img alt="${esc(name)}" data-person="${esc(name)}" style="position:absolute"></div>
        <span class="cast-name">${esc(name)}</span>
      </div>`).join("");

    const triviaHTML = (f.tr || []).map((t) => `<div class="trivia-item">${esc(t)}</div>`).join("");

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
        <div class="fs-top">
          <div class="fs-poster">
            <div class="poster-fallback">
              <span class="pf-orn">❋</span>
              <span class="pf-title">${esc(f.t)}</span>
              <span class="pf-year">${y}</span>
            </div>
            <img alt="Poster of ${esc(f.t)}" data-fs-poster style="position:absolute;inset:0">
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
              ${f.v ? `<span class="b-verdict">${esc(f.v)}</span>` : ""}
            </div>
            <div class="fs-links">
              <a class="lnk" target="_blank" rel="noopener" href="${wikiUrl}">📖 Wikipedia</a>
              <a class="lnk" target="_blank" rel="noopener" href="https://www.imdb.com/find/?q=${encodeURIComponent(searchTerm)}">⭐ IMDb</a>
              <a class="lnk spotify" target="_blank" rel="noopener" href="https://open.spotify.com/search/${encodeURIComponent(f.t + " " + (f.m || ""))}">🟢 Spotify</a>
              <a class="lnk apple" target="_blank" rel="noopener" href="https://music.apple.com/us/search?term=${encodeURIComponent(f.t + " " + y)}"> Apple Music</a>
              <a class="lnk yt" target="_blank" rel="noopener" href="https://www.jiosaavn.com/search/${encodeURIComponent(f.t)}">🎵 JioSaavn</a>
            </div>
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
          <h3>Watch <span class="hi">देखिए</span></h3>
          <div class="video-row">${videos}</div>
        </section>

        ${songsHTML ? `
        <section class="fs-section">
          <h3>The Songs <span class="hi">नग़मे</span></h3>
          <div class="song-pills">${songsHTML}</div>
        </section>` : ""}

        <p class="orn">✦ ❋ ✦</p>
      </div>`;

    layer.hidden = false;
    body.style.overflow = "hidden";
    sheet.scrollTop = 0;

    window.Wiki.poster(f, sheet.querySelector("[data-fs-poster]"), 640);
    sheet.querySelectorAll("[data-person]").forEach((img) => window.Wiki.person(img.dataset.person, img));
    sheet.querySelector(".fs-close").addEventListener("click", () => history.back());
    sheet.querySelectorAll(".video-slot").forEach((slot) => {
      slot.querySelector(".vs-cover").addEventListener("click", () => {
        slot.innerHTML = `<iframe src="${ytEmbed(slot.dataset.q)}" title="YouTube results" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
      });
    });
    sheet.querySelector(".fs-close").focus({ preventScroll: true });
  }

  function closeSheet(silent) {
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

  let lastNonFilmHash = "#/";
  function route() {
    const h = location.hash || "#/";
    const parts = h.replace(/^#\//, "").split("/").filter(Boolean);
    const view = parts[0] || "";
    if (view !== "film") {
      lastNonFilmHash = h;
      closeSheet();
    }
    switch (view) {
      case "": viewHome(); break;
      case "era": viewEra(parts[1]); break;
      case "year": viewYear(parts[1]); break;
      case "timeline": viewTimeline(); break;
      case "search": viewSearch(decodeURIComponent(parts[1] || "")); break;
      case "surprise": viewSurprise(); break;
      case "film": {
        // ensure the year view is beneath the sheet
        if (!stage.querySelector(".year-head") || !stage.innerHTML.includes(`class="year-big">${parts[1]}<`)) {
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
