class DomainError(Exception):
    """Bazowy wyjątek domenowy mapowany na odpowiedź HTTP w exception handlerze."""

    code: str = "domain_error"
    status_code: int = 500

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class ValidationError(DomainError):
    code = "validation_error"
    status_code = 422


class AuthError(DomainError):
    code = "auth_error"
    status_code = 401


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409
