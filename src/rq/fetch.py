"""Fetch + extract (§7.2). httpx -> trafilatura, Playwright fallback, with
day-1 edge cases: PDF, YouTube, Twitter/X, paywalls.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from .logging import get_logger
from .schemas import ExtractedPage

log = get_logger("fetch")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
FETCH_TIMEOUT = 10.0
MAX_REDIRECTS = 5
MIN_WORDS = 200

_STRIP_PREFIXES = ("utm_",)
_STRIP_EXACT = {"fbclid", "gclid", "mc_eid", "mc_cid", "igshid"}


# --- URL normalization ------------------------------------------------------


def canonicalize_url(url: str) -> str:
    """Strip tracking params (utm_*, fbclid, gclid) and a trailing slash.

    Pure function (no network); redirect-following happens in ``fetch_and_extract``.
    """
    parts = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k in _STRIP_EXACT or any(k.startswith(p) for p in _STRIP_PREFIXES))
    ]
    path = parts.path
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (parts.scheme, parts.netloc, path, parts.params, urlencode(query), "")
    )


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _word_count(text: str) -> int:
    return len(text.split())


def _is_youtube(url: str) -> bool:
    d = domain_of(url)
    return d in {"youtube.com", "youtu.be", "m.youtube.com"}


def _is_twitter(url: str) -> bool:
    return domain_of(url) in {"twitter.com", "x.com", "mobile.twitter.com"}


# --- extraction -------------------------------------------------------------


async def fetch_and_extract(url: str) -> ExtractedPage:
    """Returns title, author, published_at, text, word_count (§7.2)."""
    if _is_youtube(url):
        return _extract_youtube(url)
    if _is_twitter(url):
        return await _extract_twitter(url)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
    ) as client:
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            log.warning("fetch.error", url=url, error=str(e))
            return ExtractedPage(title=url, text="", word_count=0, needs_review=True)

    content_type = resp.headers.get("content-type", "").split(";")[0].strip()

    if resp.status_code in (401, 403):
        log.info("fetch.paywalled", url=url, status=resp.status_code)
        return ExtractedPage(title=url, text="", word_count=0, paywalled=True)

    if content_type == "application/pdf" or url.lower().endswith(".pdf"):
        return _extract_pdf(resp.content, url)

    html = resp.text
    page = _extract_html(html, url)

    if page.word_count < MIN_WORDS:
        rendered = await _render_with_playwright(url)
        if rendered is not None:
            page2 = _extract_html(rendered, url)
            if page2.word_count > page.word_count:
                page = page2

    if _is_paywalled(html, page):
        page.paywalled = True
    if page.word_count < MIN_WORDS:
        page.needs_review = True

    return page


def _extract_html(html: str, url: str) -> ExtractedPage:
    import trafilatura

    extracted = trafilatura.extract(
        html, output_format="json", favor_recall=True, with_metadata=True, url=url
    )
    if not extracted:
        return ExtractedPage(title=url, text="", word_count=0)
    data = json.loads(extracted)
    text = data.get("text") or ""
    return ExtractedPage(
        title=data.get("title") or url,
        author=data.get("author"),
        published_at=data.get("date"),
        text=text,
        word_count=_word_count(text),
    )


def _is_paywalled(html: str, page: ExtractedPage) -> bool:
    return 'name="article:content_tier" content="locked"' in html.replace("'", '"')


async def _render_with_playwright(url: str) -> str | None:
    """Headless Chromium fallback. Degrades gracefully if Playwright is
    unavailable (§13)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("fetch.playwright_missing", url=url)
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                pg = await browser.new_page(user_agent=USER_AGENT)
                await pg.goto(url, wait_until="networkidle", timeout=20000)
                return await pg.content()
            finally:
                await browser.close()
    except Exception as e:  # pragma: no cover - environment dependent
        log.warning("fetch.playwright_error", url=url, error=str(e))
        return None


def _extract_pdf(content: bytes, url: str) -> ExtractedPage:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    meta = reader.metadata or {}
    title = (getattr(meta, "title", None) or url) if meta else url
    page = ExtractedPage(
        title=title,
        author=getattr(meta, "author", None) if meta else None,
        text=text,
        word_count=_word_count(text),
    )
    if page.word_count < MIN_WORDS:
        page.needs_review = True
    return page


def _extract_youtube(url: str) -> ExtractedPage:
    """Transcript via youtube-transcript-api; author=channel, title=video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return ExtractedPage(title=url, text="", word_count=0, needs_review=True)

    vid = _youtube_id(url)
    if not vid:
        return ExtractedPage(title=url, text="", word_count=0, needs_review=True)
    try:
        chunks = YouTubeTranscriptApi.get_transcript(vid)
        text = " ".join(c["text"] for c in chunks)
    except Exception as e:
        log.warning("fetch.youtube_error", url=url, error=str(e))
        return ExtractedPage(title=url, text="", word_count=0, needs_review=True)
    return ExtractedPage(
        title=f"YouTube video {vid}", text=text, word_count=_word_count(text)
    )


def _youtube_id(url: str) -> str | None:
    parts = urlparse(url)
    if parts.netloc.endswith("youtu.be"):
        return parts.path.lstrip("/") or None
    qs = dict(parse_qsl(parts.query))
    return qs.get("v")


async def _extract_twitter(url: str) -> ExtractedPage:
    """Don't render Twitter/X; store URL with a thin title (§7.2)."""
    title = url
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
            resp = await client.get(
                "https://publish.twitter.com/oembed", params={"url": url}
            )
            if resp.status_code == 200:
                data = resp.json()
                author = data.get("author_name", "")
                snippet = (data.get("html", "") or "")[:80]
                title = f"{author}: {snippet}".strip(": ") or url
    except httpx.HTTPError:
        pass
    return ExtractedPage(title=title, text="", word_count=0, needs_review=True)
