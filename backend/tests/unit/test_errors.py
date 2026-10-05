import pytest

from src.core.errors import (
    AuthError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("exc_type", "code", "status"),
    [
        (NotFoundError, "not_found", 404),
        (ValidationError, "validation_error", 422),
        (AuthError, "auth_error", 401),
        (ConflictError, "conflict", 409),
    ],
)
def test_domain_errors_carry_code_and_status(
    exc_type: type[DomainError], code: str, status: int
) -> None:
    exc = exc_type("komunikat")
    assert isinstance(exc, DomainError)
    assert exc.code == code
    assert exc.status_code == status
    assert exc.message == "komunikat"
    assert str(exc) == "komunikat"
