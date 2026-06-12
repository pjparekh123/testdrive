"""Fetch + extract (§7.2), Phase 1 scope: httpx GET + trafilatura only.

Playwright fallback and the PDF/YouTube/Twitter/paywall edge cases are deferred
to a later phase (see SPEC §7.2). For now we fetch once and extract what we can.
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

_STRIP_PREFIXES = ("utm_",)
_STRIP_EXACT = {"fbclid", "gclid", "mc_eid", "mc_cid", "igshid"}


# --- URL normalization ------------------------------------------------------


def canonicalize_url(url: str) -> str:
    """Normalize for dedupe: strip tracking params (utm_*, fbclid, gclid), drop
    the fragment, and remove a trailing slash. Pure function (no network);
    redirect-following happens during the fetch.
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
    # Note the empty 6th component: the fragment (#...) is always dropped.
    return urlunparse(
        (parts.scheme, parts.netloc, path, parts.params, urlencode(query), "")
    )


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _word_count(text: str) -> int:
    return len(text.split())


# --- extraction -------------------------------------------------------------


async def fetch_and_extract(url: str) -> ExtractedPage:
    """Fetch with httpx, extract with trafilatura. Returns title, author,
    published_at, text, word_count. On any fetch/extract miss, returns an empty
    page (title = url, text = "") rather than raising.
    """
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
            return ExtractedPage(title=url, text="", word_count=0)

    if resp.status_code >= 400:
        log.warning("fetch.bad_status", url=url, status=resp.status_code)
        return ExtractedPage(title=url, text="", word_count=0)

    content_type = resp.headers.get("content-type", "").split(";")[0].strip()
    if content_type and content_type != "text/html":
        log.info("fetch.non_html", url=url, content_type=content_type)
        return ExtractedPage(title=url, text="", word_count=0)

    return _extract_html(resp.text, url)


def _extract_html(html: str, url: str) -> ExtractedPage:
    import trafilatura

    extracted = trafilatura.extract(
        html, output_format="json", favor_recall=True, with_metadata=True, url=url
    )
    if not extracted:
        log.info("fetch.no_extract", url=url)
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
