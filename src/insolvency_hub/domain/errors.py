class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str, *, basis: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.basis = basis


class ValidationFailed(DomainError):
    code = "validation_failed"


class TransitionNotAllowed(DomainError):
    code = "transition_not_allowed"


class NotFound(DomainError):
    code = "not_found"


class VersionConflict(DomainError):
    code = "version_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected version {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual
