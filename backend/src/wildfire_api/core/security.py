from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from wildfire_api.core.request_context import get_request_id


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class FixedWindowRateLimiter:
    """Process-local fixed-window limiter with bounded stale-client cleanup."""

    def __init__(
        self,
        *,
        per_client_limit: int,
        global_limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._per_client_limit = per_client_limit
        self._global_limit = global_limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._window_started = clock()
        self._global_count = 0
        self._clients: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check(self, client_id: str) -> LimitDecision:
        async with self._lock:
            now = self._clock()
            elapsed = now - self._window_started
            if elapsed >= self._window_seconds:
                self._window_started = now
                self._global_count = 0
                self._clients.clear()
                elapsed = 0
            retry_after = max(1, math.ceil(self._window_seconds - elapsed))
            client_count = self._clients.get(client_id, 0)
            if self._global_count >= self._global_limit or client_count >= self._per_client_limit:
                return LimitDecision(False, retry_after)
            self._global_count += 1
            self._clients[client_id] = client_count + 1
            return LimitDecision(True)


class ConcurrencyLimiter:
    """Reject excess work immediately instead of building an unbounded wait queue."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            self._active = max(0, self._active - 1)


def pseudonymous_client_id(request: Request, salt: str) -> str:
    # Do not trust forwarding headers here: the deployment proxy must pass the real peer
    # address to the ASGI server using an explicit trusted-proxy configuration.
    address = request.client.host if request.client else "unknown"
    key = salt.encode() if salt else b"ephemeral-development-salt"
    return hmac.new(key, address.encode(), hashlib.sha256).hexdigest()[:24]


class RequestTimeoutMiddleware:
    """Hard ASGI deadline that buffers output so a timeout can remain a valid JSON response."""

    def __init__(self, app: ASGIApp, *, timeout_seconds: float, health_path: str) -> None:
        self._app = app
        self._timeout_seconds = timeout_seconds
        self._health_path = health_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == self._health_path:
            await self._app(scope, receive, send)
            return
        messages: list[Message] = []

        async def buffered_send(message: Message) -> None:
            messages.append(message)

        try:
            await asyncio.wait_for(
                self._app(scope, receive, buffered_send), timeout=self._timeout_seconds
            )
        except TimeoutError:
            request_id = get_request_id()
            response = JSONResponse(
                status_code=504,
                content={
                    "request_id": request_id,
                    "error": {
                        "code": "REQUEST_TIMEOUT",
                        "message": "Request processing timed out.",
                    },
                },
            )
            await response(scope, receive, send)
            return
        for message in messages:
            await send(message)


class RequestBodyLimitMiddleware:
    """Cap the actual ASGI body, including chunked requests without Content-Length."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self._max_body_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={
                            "request_id": get_request_id(),
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Request payload is too large.",
                            },
                        },
                    )
                    await response(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self._app(scope, replay, send)
