from datetime import UTC, datetime, timedelta

from src.sources.base import SourceState, TrackedAsset, since_for
from src.sources.dedup import normalize_url, strip_html, title_hash

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def asset(ticker: str, asset_type: str) -> TrackedAsset:
    return TrackedAsset(id="a1", ticker=ticker, name="X", asset_type=asset_type)


def test_market_from_asset() -> None:
    assert asset("BTC", "crypto").market == "crypto"
    assert asset("AAPL", "stock").market == "us"
    assert asset("SPY", "etf").market == "us"
    assert asset("BRK.B", "stock").market == "us"  # klasa akcji, nie giełda
    assert asset("CDR.WA", "stock").market == "gpw"
    assert asset("VWCE.DE", "etf").market == "eu_etf"
    assert asset("VOD.L", "stock").market == "eu_etf"


def test_since_for_new_key_uses_lookback() -> None:
    assert since_for("rss:x", {}, NOW, 72) == NOW - timedelta(hours=72)


def test_since_for_known_key_uses_last_fetch_with_overlap() -> None:
    states = {"rss:x": SourceState(key="rss:x", last_fetched_at=NOW - timedelta(hours=1))}
    assert since_for("rss:x", states, NOW, 72) == NOW - timedelta(hours=1, minutes=10)


def test_normalize_url_strips_tracking() -> None:
    raw = (
        "https://www.bankier.pl/wiadomosc/Orlen-9207763.html"
        "?utm_source=RSS&utm_medium=RSS&utm_campaign=Gielda#komentarze"
    )
    assert normalize_url(raw) == "https://www.bankier.pl/wiadomosc/Orlen-9207763.html"


def test_normalize_url_keeps_meaningful_query_and_lowercases_host() -> None:
    assert normalize_url("HTTPS://Example.COM/a/?id=5&fbclid=zz") == "https://example.com/a?id=5"
    assert normalize_url("https://example.com") == "https://example.com/"


def test_title_hash_ignores_case_and_punctuation() -> None:
    assert title_hash("Orlen, KGHM i PKO szarpnęły!") == title_hash("orlen kghm i pko  szarpnęły")
    assert title_hash("Orlen rośnie") != title_hash("Orlen spada")


def test_strip_html_removes_tags_and_entities() -> None:
    html = '<p><img src="x.jpg" alt="" />Sesja na&nbsp;GPW &amp; wzrosty</p>'
    assert strip_html(html) == "Sesja na GPW & wzrosty"
