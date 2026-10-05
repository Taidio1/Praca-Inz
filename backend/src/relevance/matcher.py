"""Tani matching encji (spec §4 pkt 1): tickery, nazwy, słowa kluczowe, wyrażenia mylące."""

import re
from dataclasses import dataclass

from src.relevance.profiles import AssetProfile

TITLE_HIT = 1.0
SNIPPET_HIT = 0.7
KEYWORD_HIT = 0.4
HINT_FLOOR = 0.4
_MIN_KEYWORD = 3
_GPW_SUFFIX = r"\w{0,4}"  # odmiana: Orlen -> Orlenu, Orlenem


@dataclass(frozen=True)
class MatchResult:
    score: float
    hits: tuple[str, ...]


def _phrase(text: str, suffix: str, flags: int) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(text)}{suffix}(?!\w)", flags)


class Matcher:
    def __init__(self, profile: AssetProfile) -> None:
        suffix = _GPW_SUFFIX if profile.market == "gpw" else ""
        # Nazwy porównujemy bez względu na wielkość liter, więc warianty "NVIDIA"/"Nvidia"
        # to jedno trafienie (pierwszy wariant z profilu).
        unique_names: dict[str, str] = {}
        for name in profile.names:
            unique_names.setdefault(name.casefold(), name)
        self._names = [(n, _phrase(n, suffix, re.IGNORECASE)) for n in unique_names.values()]
        self._tickers = [(t, _phrase(t, "", 0)) for t in profile.ticker_patterns]
        self._negatives = [_phrase(n, "", re.IGNORECASE) for n in profile.negative_terms]
        self._keywords = [
            (k, _phrase(k, suffix, re.IGNORECASE))
            for k in profile.keywords
            if len(k) >= _MIN_KEYWORD
        ]

    def _mask(self, text: str) -> str:
        for pattern in self._negatives:
            text = pattern.sub(lambda m: " " * len(m.group(0)), text)
        return text

    def _identity_hits(self, text: str, where: str) -> list[str]:
        hits = [f'ticker "{t}" w {where}' for t, p in self._tickers if p.search(text)]
        hits += [f'nazwa "{n}" w {where}' for n, p in self._names if p.search(text)]
        return hits

    def match(self, title: str, snippet: str | None, hinted: bool) -> MatchResult:
        t = self._mask(title)
        s = self._mask(snippet or "")
        hits = self._identity_hits(t, "tytule")
        score = TITLE_HIT if hits else 0.0
        if not hits:
            hits = self._identity_hits(s, "opisie")
            score = SNIPPET_HIT if hits else 0.0
        if score == 0.0:
            both = f"{t} {s}"
            found = [k for k, p in self._keywords if p.search(both)]
            if len(found) >= 2:
                score = KEYWORD_HIT
                hits = [f"słowa kluczowe: {', '.join(found)}"]
        if hinted and score < HINT_FLOOR:
            score = HINT_FLOOR
            hits.append("wskazanie źródła")
        return MatchResult(score=score, hits=tuple(hits))
