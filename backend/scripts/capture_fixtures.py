"""Zapisuje prawdziwe odpowiedzi źródeł newsów jako fixture'y testów.

Uruchomienie: cd backend && python scripts/capture_fixtures.py
Wymaga FINNHUB_API_KEY w .env (dla company-news). Zasada projektu: testy parserów
opierają się na prawdziwych odpowiedziach, nie na wymyślonych danych.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from src.core.config import get_settings

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sources"
UA = {"User-Agent": "Mozilla/5.0 (Opes research tool)"}
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

RSS = {
    "rss_bankier_gielda.xml": "https://www.bankier.pl/rss/gielda.xml",
    "rss_stooq_biznes.xml": "https://static.stooq.pl/rss/pl/b.rss",
    "rss_coindesk.xml": "https://www.coindesk.com/arc/outboundfeeds/rss/",
}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=UA) as http:
        for name, url in RSS.items():
            res = await http.get(url)
            res.raise_for_status()
            (OUT / name).write_bytes(res.content)
            print(f"{name}: {len(res.content)} B")

        today = datetime.now(UTC).date()
        res = await http.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": "AAPL",
                "from": (today - timedelta(days=2)).isoformat(),
                "to": today.isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        res.raise_for_status()
        (OUT / "finnhub_company_news_AAPL.json").write_text(res.text, encoding="utf-8")
        print(f"finnhub: {len(res.json())} artykułów")

        params = {
            "query": '("CD Projekt" OR "Orlen") sourcelang:polish',
            "mode": "artlist",
            "format": "json",
            "maxrecords": "20",
            "sort": "datedesc",
            "timespan": "3d",
        }
        await asyncio.sleep(6)
        res = await http.get(GDELT, params=params)
        (OUT / "gdelt_artlist_polish.json").write_text(res.text, encoding="utf-8")
        print(f"gdelt: HTTP {res.status_code}, {len(res.text)} B")

        # Celowo dwa zapytania bez odstępu: GDELT odpowiada wtedy tekstem o limicie.
        await http.get(GDELT, params=params)
        res = await http.get(GDELT, params=params)
        (OUT / "gdelt_rate_limit.txt").write_text(res.text, encoding="utf-8")
        print(f"gdelt limit: HTTP {res.status_code}: {res.text[:60]!r}")


if __name__ == "__main__":
    asyncio.run(main())
