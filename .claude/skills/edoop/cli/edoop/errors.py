"""Exception hierarchy for edoop-cli."""

from __future__ import annotations


class EdoopError(Exception):
    """Base class for all edoop-cli errors."""


class ConfigError(EdoopError):
    """Configuration is missing or invalid (e.g. no credentials)."""


class AuthError(EdoopError):
    """Login failed or the stored session is no longer valid."""


class NotLoggedInError(AuthError):
    """No usable session is available; the user must run ``edoop login`` first."""


class ApiError(EdoopError):
    """The edoop API returned an unexpected/error response.

    Attributes:
        status_code: HTTP status code of the response, if available.
        payload: Parsed JSON body or raw text of the response, if available.
    """

    def __init__(self, message: str, status_code: int | None = None, payload: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class EndpointNotConfiguredError(EdoopError):
    """A high-level command needs an endpoint that is not known/configured.

    Raised so the CLI can point the user at ``edoop api`` and the endpoint
    override mechanism instead of failing with an opaque traceback.
    """
