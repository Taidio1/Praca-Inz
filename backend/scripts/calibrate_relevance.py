"""Rozkład podobieństw embeddingów: pary dopasowane vs losowe (kalibracja COSINE_FLOOR/CEILING).

Uruchomienie: cd backend && .venv/Scripts/python scripts/calibrate_relevance.py
Wymaga profili z embeddingiem (ANTHROPIC_API_KEY) i ocenionych itemów w bazie.
"""

import asyncio
import random
import statistics

from supabase import acreate_client

from src.core.config import get_settings
from src.relevance.embedder import LocalEmbedder, cosine, item_text
from src.relevance.profiles import profile_from_row


def quantiles(values: list[float]) -> str:
    if len(values) < 5:
        return f"za mało danych (n={len(values)})"
    q = statistics.quantiles(values, n=10)
    return f"n={len(values)} p10={q[0]:.3f} p50={q[4]:.3f} p90={q[8]:.3f}"


async def main() -> None:
    s = get_settings()
    c = await acreate_client(s.supabase_url, s.supabase_service_role_key)
    profiles = [profile_from_row(r) for r in
                (await c.table("asset_profiles").select("*").execute()).data]
    profiles = [p for p in profiles if p.embedding]
    if not profiles:
        raise SystemExit("Brak profili z embeddingiem: dodaj ANTHROPIC_API_KEY i uruchom cykl")
    rel = (await c.table("item_relevance").select("match_score, embedding_score")
           .not_.is_("embedding_score", "null").limit(5000).execute()).data
    title_hits = [r["embedding_score"] for r in rel if r["match_score"] == 1.0]
    weak_hits = [r["embedding_score"] for r in rel if r["match_score"] < 1.0]

    items = (await c.table("source_items").select("title, snippet")
             .is_("duplicate_of", "null").limit(2000).execute()).data
    sample = random.Random(42).sample(items, min(200, len(items)))
    vectors = await LocalEmbedder(s.embedding_model).embed(
        [item_text(i["title"], i["snippet"]) for i in sample])
    random_pairs = [cosine(v, p.embedding) for v in vectors for p in profiles
                    if p.embedding is not None]

    print("trafienie w tytule (match=1.0):", quantiles(title_hits))
    print("słabe dopasowanie (match<1.0): ", quantiles(weak_hits))
    print("losowe pary item×profil:       ", quantiles(random_pairs))
    print("Sugestia: COSINE_FLOOR ≈ p90 losowych, COSINE_CEILING ≈ p90 trafień w tytule.")


if __name__ == "__main__":
    asyncio.run(main())
