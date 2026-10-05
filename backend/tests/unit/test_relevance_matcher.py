from src.relevance.matcher import Matcher
from src.relevance.profiles import AssetProfile


def profile(names: tuple[str, ...], tickers: tuple[str, ...] = (), market: str = "us",
            negative: tuple[str, ...] = (), keywords: tuple[str, ...] = ()) -> AssetProfile:
    return AssetProfile(asset_id="a", names=names, ticker_patterns=tickers,
                        negative_terms=negative, keywords=keywords, market=market,  # type: ignore[arg-type]
                        profile_text="x", embedding=None, generated_by="llm")


# Prawdziwe tytuły (Bankier, CoinDesk, Finnhub; pobrane 2026-10-05)
BANKIER = "Orlen, KGHM i PKO szarpnęły indeksem blue chipów. Wyborcze wzrosty w Europie i Ameryce"
COINDESK_BTC = (
    "Metaplanet added 1,000 bitcoin net in the third quarter bringing holdings to 44,000 BTC"
)
COINDESK_ETH = "SEC approves a 3x fix for bitcoin and ether traders who miss the wild swings"
NVIDIA = "Nvidia stock nears record highs on Foxconn numbers. Cerebras rises on Altman comments"


def test_name_in_title_scores_full() -> None:
    r = Matcher(profile(("Orlen",), market="gpw")).match(BANKIER, None, hinted=False)
    assert r.score == 1.0 and any("Orlen" in h for h in r.hits)


def test_ticker_is_case_sensitive_with_word_boundaries() -> None:
    m = Matcher(profile(("Bitcoin",), ("BTC",), market="crypto"))
    assert m.match(COINDESK_BTC, None, hinted=False).score == 1.0
    eth = Matcher(profile(("Ethereum",), ("ETH",), market="crypto"))
    assert eth.match("Ethernet switch maker beats estimates", None, hinted=False).score == 0.0
    assert eth.match("eth", None, hinted=False).score == 0.0


def test_gpw_inflection_only_for_gpw_market() -> None:
    title = "Akcjonariusze Orlenu zdecydują o dywidendzie"
    assert Matcher(profile(("Orlen",), market="gpw")).match(title, None, False).score == 1.0
    assert Matcher(profile(("Apple",), market="us")).match("Applebee's sales", None,
                                                           False).score == 0.0


def test_negative_terms_mask_name_hits() -> None:
    m = Matcher(profile(("PKO",), market="gpw", negative=("PKO TFI",)))
    assert m.match("PKO TFI uruchamia nowy fundusz", None, False).score == 0.0
    assert m.match(BANKIER, None, False).score == 1.0  # samo "PKO" nadal trafia


def test_snippet_only_hit_scores_lower() -> None:
    m = Matcher(profile(("Nvidia",)))
    r = m.match("Tech stocks edge higher as bond yields remain elevated", "Nvidia led gains.",
                hinted=False)
    assert r.score == 0.7


def test_keywords_need_two_distinct_hits() -> None:
    m = Matcher(profile(("Ethereum",), keywords=("ether", "staking", "DeFi")))
    assert m.match(COINDESK_ETH, None, False).score == 0.0  # tylko "ether"
    assert m.match(COINDESK_ETH, "Staking yields fell.", False).score == 0.4


def test_hint_floor() -> None:
    m = Matcher(profile(("Apple",), ("AAPL",)))
    assert m.match(NVIDIA, None, hinted=True).score == 0.4
    assert m.match(NVIDIA, None, hinted=False).score == 0.0


def test_regex_special_chars_in_names_are_literal() -> None:
    m = Matcher(profile(("S&P 500",), market="eu_etf"))
    assert m.match("Stock Market Today: Dow Futures Gain. S&P 500 rises", None, False).score == 1.0


def test_case_variants_of_a_name_are_one_hit() -> None:
    # Profil z LLM zawiera "NVIDIA" i "Nvidia"; w powodzie oceny ma być jedno trafienie.
    m = Matcher(profile(("NVIDIA", "Nvidia", "NVIDIA Corp")))
    r = m.match(NVIDIA, None, hinted=False)
    assert r.hits == ('nazwa "NVIDIA" w tytule',)
