"""Exception hierarchy. Everything the SDK raises on purpose derives from MyorlenError."""

from __future__ import annotations


class MyorlenError(Exception):
    """Base class for all SDK errors."""


class AuthenticationError(MyorlenError):
    """Login failed (bad credentials, blocked account) or the session could not be re-established."""


class ParseError(MyorlenError):
    """A response did not have the expected structure (the API probably changed)."""


class ApiError(MyorlenError):
    """An endpoint answered with an HTTP error or a non-zero ``Code``."""

    def __init__(self, message: str, payload: object = None, code: int | None = None) -> None:
        super().__init__(message)
        self.payload = payload
        self.code = code


class NotFoundError(MyorlenError):
    """The requested meter point / agreement / invoice is not on this account, or several exist
    and none was chosen."""
