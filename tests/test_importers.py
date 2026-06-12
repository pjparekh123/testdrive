from __future__ import annotations

from rq.importers import parse_export, parse_instapaper, parse_pocket

POCKET_HTML = """<!DOCTYPE html>
<html><head><title>Pocket Export</title></head><body>
<h1>Unread</h1>
<ul>
<li><a href="https://example.com/a" time_added="1609459200" tags="rust,systems">A</a></li>
<li><a href="https://example.com/b?utm_source=pocket" time_added="1609459300" tags="">B</a></li>
</ul>
<h1>Read Archive</h1>
<ul>
<li><a href="https://example.com/a" tags="dup">A again (dup)</a></li>
<li><a href="ftp://skip.me/x">non-http</a></li>
</ul>
</body></html>
"""

INSTAPAPER_CSV = """URL,Title,Selection,Folder
https://example.com/x,First,,Unread
https://example.com/y,Second,a quote,Archive
not-a-url,Bad,,Unread
https://example.com/x,Dup,,Starred
"""


def test_parse_pocket(tmp_path):
    p = tmp_path / "pocket_export.html"
    p.write_text(POCKET_HTML)
    urls = parse_pocket(p)
    assert urls == [
        "https://example.com/a",
        "https://example.com/b?utm_source=pocket",
    ]  # deduped, http(s) only, ftp skipped


def test_parse_instapaper(tmp_path):
    p = tmp_path / "instapaper-export.csv"
    p.write_text(INSTAPAPER_CSV)
    urls = parse_instapaper(p)
    assert urls == ["https://example.com/x", "https://example.com/y"]  # deduped, bad row skipped


def test_parse_instapaper_with_bom(tmp_path):
    p = tmp_path / "ip.csv"
    p.write_bytes("﻿".encode("utf-8") + INSTAPAPER_CSV.encode("utf-8"))
    assert parse_instapaper(p) == ["https://example.com/x", "https://example.com/y"]


def test_parse_export_dispatch(tmp_path):
    (tmp_path / "x.html").write_text(POCKET_HTML)
    (tmp_path / "x.csv").write_text(INSTAPAPER_CSV)
    assert len(parse_export(tmp_path / "x.html")) == 2
    assert len(parse_export(tmp_path / "x.csv")) == 2
    import pytest

    with pytest.raises(ValueError):
        parse_export(tmp_path / "x.txt")
