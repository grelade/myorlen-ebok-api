"""Exception hierarchy. Everything the SDK raises on purpose derives from PgnigError."""

from __future__ import annotations


class PgnigError(Exception):
    """Base class for all SDK errors."""


class AuthenticationError(PgnigError):
    """Login failed (bad credentials, blocked account) or the session could not be re-established."""


class ParseError(PgnigError):
    """A response did not have the expected structure (the API probably changed)."""


class ApiError(PgnigError):
    """An endpoint answered with an HTTP error or a non-zero ``Code``."""

    def __init__(self, message: str, payload: object = None, code: int | None = None) -> None:
        super().__init__(message)
        self.payload = payload
        self.code = code


class NotFoundError(PgnigError):
    """The requested meter point / agreement / invoice is not on this account, or several exist
    and none was chosen."""
