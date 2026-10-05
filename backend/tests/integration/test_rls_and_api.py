from fastapi import FastAPI

from tests.integration.conftest import api, bearer, pytestmark  # noqa: F401


async def test_full_portfolio_flow_and_rls_isolation(
    app: FastAPI, two_user_tokens: tuple[str, str]
) -> None:
    token_a, token_b = two_user_tokens
    async with api(app) as client:
        # A dodaje pozycję (AAPL z seed.sql)
        res = await client.post(
            "/api/v1/portfolio",
            json={"ticker": "AAPL", "asset_type": "stock", "quantity": 10},
            headers=bearer(token_a),
        )
        assert res.status_code == 201, res.text
        position_id = res.json()["id"]

        # A widzi swoją pozycję
        res = await client.get("/api/v1/portfolio", headers=bearer(token_a))
        assert [p["asset"]["ticker"] for p in res.json()] == ["AAPL"]

        # B nie widzi pozycji A (RLS)
        res = await client.get("/api/v1/portfolio", headers=bearer(token_b))
        assert res.json() == []

        # B nie może usunąć pozycji A (RLS => delete zwraca 0 wierszy => 404)
        res = await client.delete(f"/api/v1/portfolio/{position_id}", headers=bearer(token_b))
        assert res.status_code == 404

        # A może usunąć własną pozycję
        res = await client.delete(f"/api/v1/portfolio/{position_id}", headers=bearer(token_a))
        assert res.status_code == 204

        # Duplikat: A dodaje dwa razy to samo aktywo => 409
        for expected in (201, 409):
            res = await client.post(
                "/api/v1/portfolio",
                json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1},
                headers=bearer(token_a),
            )
            assert res.status_code == expected


async def test_feed_empty_for_fresh_user(app: FastAPI, two_user_tokens: tuple[str, str]) -> None:
    token_a, _ = two_user_tokens
    async with api(app) as client:
        res = await client.get("/api/v1/feed", headers=bearer(token_a))
    assert res.status_code == 200
    assert res.json() == {"items": [], "next_cursor": None}


async def test_settings_lazy_create_and_update(
    app: FastAPI, two_user_tokens: tuple[str, str]
) -> None:
    token_a, _ = two_user_tokens
    async with api(app) as client:
        res = await client.get("/api/v1/settings", headers=bearer(token_a))
        assert res.status_code == 200
        assert res.json()["relevance_threshold"] == 0.5

        res = await client.put(
            "/api/v1/settings",
            json={"relevance_threshold": 0.7},
            headers=bearer(token_a),
        )
        assert res.json()["relevance_threshold"] == 0.7
