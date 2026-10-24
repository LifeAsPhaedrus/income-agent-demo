"""Shared redirect refusal for authenticated and loopback HTTP clients."""

from urllib.request import HTTPRedirectHandler


class SourceConnectionError(ValueError):
    """A safe-to-display source connection failure."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise SourceConnectionError("Redirect refused; credentials never forwarded")
