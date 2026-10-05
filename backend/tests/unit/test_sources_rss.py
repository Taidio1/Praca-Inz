from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.sources.base import SourceState, TrackedAsset
from src.sources.dedup import normalize_url
from src.sources.rss import RssSource, parse_feed

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
OLD = datetime(2000, 1, 1, tzinfo=UTC)
CDR = TrackedAsset(id="a-cdr", ticker="CDR.WA", name="CD Projekt", asset_type="stock")
BTC = TrackedAsset(id="a-btc", ticker="BTC", name="Bitcoin", asset_type="crypto")
FEEDS = {
    "gpw": ("https://www.bankier.pl/rss/gielda.xml",),
    "crypto": ("https://www.coindesk.com/arc/outboundfeeds/rss/",),
}


def test_parse_feed_reads_real_bankier_items() -> None:
    items = parse_feed((FIX / "rss_bankier_gielda.xml").read_bytes(), "bankier", OLD)
    assert len(items) > 0
    for it in items:
        assert it.source == "rss"
        assert it.url.startswith("https://")
        assert it.title and "<" not in it.title
        assert it.published_at is not None and it.published_at.tzinfo is not None
        assert it.raw["feed"] == "bankier"


def test_parse_feed_snippets_have_no_html() -> None:
    items = parse_feed((FIX / "rss_bankier_gielda.xml").read_bytes(), "bankier", OLD)
    snippets = [it.snippet for it in items if it.snippet]
    assert snippets, "Bankier ma opisy z HTML: po czyszczeniu nie mogą zniknąć"
    assert all("<" not in s and "&amp;" not in s for s in snippets)
    assert all(len(s) <= 1000 for s in snippets)


def test_bankier_links_are_normalized_in_ingest_rows() -> None:
    items = parse_feed((FIX / "rss_bankier_gielda.xml").read_bytes(), "bankier", OLD)
    assert any("utm_" in it.url for it in items)  # surowy link z feedu ma utm_*
    assert all("utm_" not in normalize_url(it.url) for it in items)


def test_parse_feed_drops_items_older_than_cutoff() -> None:
    content = (FIX / "rss_stooq_biznes.xml").read_bytes()
    all_items = parse_feed(content, "stooq", OLD)
    times = sorted({it.published_at for it in all_items if it.published_at})
    assert len(times) > 1, "fixture stooq powinien mieć itemy z różnymi datami"
    cutoff = times[len(times) // 2]
    recent = parse_feed(content, "stooq", cutoff)
    assert 0 < len(recent) < len(all_items)
    assert all(it.published_at is None or it.published_at >= cutoff for it in recent)


def make_transport(
    responses: dict[str, httpx.Response], seen: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[str(request.url)]

    return httpx.MockTransport(handler)


async def test_fetches_only_feeds_for_tracked_markets() -> None:
    seen: list[httpx.Request] = []
    body = (FIX / "rss_bankier_gielda.xml").read_bytes()
    responses = {FEEDS["gpw"][0]: httpx.Response(200, content=body, headers={"ETag": '"e1"'})}
    async with httpx.AsyncClient(transport=make_transport(responses, seen)) as http:
        source = RssSource(http, FEEDS, lookback_hours=24 * 365 * 30)
        result = await source.fetch([CDR], {}, datetime.now(UTC))
    assert [str(r.url) for r in seen] == [FEEDS["gpw"][0]]
    assert len(result.items) > 0
    assert result.ok == {f"rss:{FEEDS['gpw'][0]}": ('"e1"', None)}
    assert result.errors == {}


async def test_sends_etag_and_handles_304() -> None:
    seen: list[httpx.Request] = []
    url = FEEDS["gpw"][0]
    responses = {url: httpx.Response(304)}
    states = {f"rss:{url}": SourceState(key=f"rss:{url}", etag='"e1"', last_modified="Mon")}
    async with httpx.AsyncClient(transport=make_transport(responses, seen)) as http:
        result = await RssSource(http, FEEDS).fetch([CDR], states, datetime.now(UTC))
    assert seen[0].headers["If-None-Match"] == '"e1"'
    assert seen[0].headers["If-Modified-Since"] == "Mon"
    assert result.items == []
    assert result.ok == {f"rss:{url}": ('"e1"', "Mon")}


async def test_one_feed_failure_does_not_block_others() -> None:
    seen: list[httpx.Request] = []
    body = (FIX / "rss_coindesk.xml").read_bytes()
    responses = {
        FEEDS["gpw"][0]: httpx.Response(404),
        FEEDS["crypto"][0]: httpx.Response(200, content=body),
    }
    async with httpx.AsyncClient(transport=make_transport(responses, seen)) as http:
        source = RssSource(http, FEEDS, lookback_hours=24 * 365 * 30)
        result = await source.fetch([CDR, BTC], {}, datetime.now(UTC))
    assert f"rss:{FEEDS['gpw'][0]}" in result.errors
    assert f"rss:{FEEDS['crypto'][0]}" in result.ok
    assert len(result.items) > 0


async def test_late_appearing_old_items_are_not_cut_by_last_fetch() -> None:
    # Item z pubDate sprzed ostatniego pobrania, który pojawił się w feedzie później,
    # nie może przepaść: odcinamy tylko po stałym oknie wstecz, duplikaty odsiewa baza.
    seen: list[httpx.Request] = []
    url = FEEDS["gpw"][0]
    body = (FIX / "rss_bankier_gielda.xml").read_bytes()
    now = datetime.now(UTC)
    states = {f"rss:{url}": SourceState(key=f"rss:{url}", last_fetched_at=now)}
    async with httpx.AsyncClient(
        transport=make_transport({url: httpx.Response(200, content=body)}, seen)
    ) as http:
        source = RssSource(http, FEEDS, lookback_hours=24 * 365 * 30)
        result = await source.fetch([CDR], states, now)
    assert len(result.items) > 0
