"""The transport seam: how a model adapter's request reaches a provider
(Arc 2 R2; claude/context/runtime-contract.md §5.1).

A transport is one callable, handed to the adapter at construction:

    transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None)
        -> (status: int, headers: Mapping[str, str], chunks: Iterable[bytes])

`headers` come back with lowercase names; `chunks` is the response body in
pieces split anywhere — byte by byte included — and the adapter's readers
do not care where. A transport raises for a failure to talk at all:
TimeoutError (a socket timeout), ConnectionError or another OSError (the
connection refused, reset, a TLS failure — and TransportError, below, for a
broken HTTP exchange). Iterating `chunks` may raise the same, mid-stream.

Two transports exist: the tests' — recorded bytes, built from the
fixtures under fixtures/anthropic/ (T8: twine's tests never reach a model
API) — and `https_transport`, this module's, the real one, which the
Anthropic adapter builds when it is given none. **This module is the only
place twine opens a socket**: nothing else under twine/ imports http.client,
ssl or socket, and tests/test_runtime.py walks the imports to hold that
(this file is its one named exception). It reads no environment and no
key: the headers it sends are the ones it is handed, and it never logs
them. stdlib only.
"""

from __future__ import annotations

import http.client
import logging
import ssl
from typing import Callable, Iterable, Iterator, Mapping, Tuple
from urllib.parse import urlsplit

log = logging.getLogger("twine.runtime.transport")

# What a transport answers with: the status, the headers (lowercase names),
# and the body in chunks.
Response = Tuple[int, Mapping[str, str], Iterable[bytes]]
Transport = Callable[[str, str, Mapping[str, str], "bytes | None"], Response]

# How long the real transport waits on the socket — for the connection and
# for each read — before TimeoutError. A streamed turn's reads arrive as
# the model writes (and `ping` events keep an idle stream alive), so this
# bounds silence, not the length of a turn.
DEFAULT_TIMEOUT = 600.0
READ_SIZE = 65536


class TransportError(ConnectionError):
    """A broken HTTP exchange the stdlib reported as an
    http.client.HTTPException (a bad status line, a truncated chunked
    body, an incomplete read): a connection failure as far as the adapter
    is concerned. The message names the stdlib's exception, never a
    header."""


def _headers(response: http.client.HTTPResponse) -> dict[str, str]:
    """The response's headers with lowercase names; a header sent twice
    is joined with ", " (RFC 9110 §5.3), so nothing is dropped."""
    out: dict[str, str] = {}
    for name, value in response.getheaders():
        key = name.lower()
        out[key] = f"{out[key]}, {value}" if key in out else value
    return out


def _chunks(connection: http.client.HTTPSConnection, response: http.client.HTTPResponse,
            read_size: int) -> Iterator[bytes]:
    """The body as it arrives — read1 hands back what is buffered without
    waiting for a full block, so a stream's events reach the reader as the
    provider sends them. Closes the connection when the body ends or the
    reader stops."""
    try:
        while True:
            try:
                piece = response.read1(read_size)
            except http.client.HTTPException as exc:
                raise TransportError(f"the response body broke: {type(exc).__name__}: "
                                     f"{exc}") from None
            if not piece:
                return
            yield piece
    finally:
        connection.close()


def https_transport(*, timeout: float = DEFAULT_TIMEOUT,
                    read_size: int = READ_SIZE) -> Transport:
    """The real transport: HTTPS through http.client, the system's trust
    store (ssl.create_default_context), one connection per request.

    No retries (the loop's, R4), no redirects, no proxy: the request goes
    to the URL's host. Raises ValueError for a URL that is not https."""
    context = ssl.create_default_context()

    def transport(method: str, url: str, headers: Mapping[str, str],
                  body: bytes | None) -> Response:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError(f"the transport speaks https only, not {url!r}")
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout,
                                                 context=context)
        log.debug("%s https://%s%s (%d body bytes)", method, parts.hostname, path,
                  len(body or b""))
        try:
            connection.request(method, path, body=body, headers=dict(headers))
            response = connection.getresponse()
        except http.client.HTTPException as exc:
            connection.close()
            raise TransportError(f"the exchange broke: {type(exc).__name__}: {exc}") from None
        except BaseException:
            connection.close()
            raise
        log.debug("%s %s: status %d", method, path, response.status)
        return response.status, _headers(response), _chunks(connection, response, read_size)

    return transport


__all__ = ["DEFAULT_TIMEOUT", "Response", "Transport", "TransportError", "https_transport"]
