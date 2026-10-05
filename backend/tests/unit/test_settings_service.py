from src.schemas.settings import SettingsUpdate
from src.services.settings import SettingsService

USER_ID = "11111111-1111-1111-1111-111111111111"


class FakeSettingsRepo:
    def __init__(self) -> None:
        self.row: dict | None = None  # type: ignore[type-arg]

    async def get(self) -> dict | None:  # type: ignore[type-arg]
        return self.row

    async def create_defaults(self, user_id: str) -> dict:  # type: ignore[type-arg]
        self.row = {"user_id": user_id, "relevance_threshold": 0.5, "notifications": {}}
        return self.row

    async def update(self, user_id: str, fields: dict) -> dict:  # type: ignore[type-arg]
        assert self.row is not None
        self.row.update(fields)
        return self.row


async def test_get_creates_defaults_on_first_read() -> None:
    repo = FakeSettingsRepo()
    out = await SettingsService(repo).get(USER_ID)
    assert out.relevance_threshold == 0.5
    assert repo.row is not None


async def test_get_returns_existing_row() -> None:
    repo = FakeSettingsRepo()
    repo.row = {"user_id": USER_ID, "relevance_threshold": 0.8, "notifications": {}}
    out = await SettingsService(repo).get(USER_ID)
    assert out.relevance_threshold == 0.8


async def test_update_changes_only_provided_fields() -> None:
    repo = FakeSettingsRepo()
    svc = SettingsService(repo)
    await svc.get(USER_ID)  # lazy create
    out = await svc.update(USER_ID, SettingsUpdate(relevance_threshold=0.7))
    assert out.relevance_threshold == 0.7
    assert out.notifications == {}


async def test_update_with_empty_payload_returns_current() -> None:
    repo = FakeSettingsRepo()
    svc = SettingsService(repo)
    await svc.get(USER_ID)
    out = await svc.update(USER_ID, SettingsUpdate())
    assert out.relevance_threshold == 0.5


async def test_base_currency_defaults_to_pln_and_can_be_changed() -> None:
    repo = FakeSettingsRepo()
    svc = SettingsService(repo)
    assert (await svc.get(USER_ID)).base_currency == "PLN"
    out = await svc.update(USER_ID, SettingsUpdate(base_currency="EUR"))
    assert out.base_currency == "EUR"
    assert repo.row is not None and repo.row["base_currency"] == "EUR"


def test_base_currency_outside_pln_usd_eur_is_rejected() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SettingsUpdate(base_currency="GBP")  # type: ignore[arg-type]
