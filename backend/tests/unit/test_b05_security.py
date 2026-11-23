import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from wildfire_api.core.config import Settings
from wildfire_api.core.logging import JsonFormatter
from wildfire_api.core.security import ConcurrencyLimiter, FixedWindowRateLimiter
from wildfire_api.main import create_app


def test_per_client_quota_returns_typed_429_and_keeps_health_available() -> None:
    settings = Settings(
        environment="test",
        log_level="WARNING",
        per_client_requests_per_minute=1,
        global_requests_per_minute=2,
    )
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/api/v1/metadata").status_code == 200
        limited = client.get("/api/v1/metadata")
        health = client.get("/api/v1/health")

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["request_id"] == limited.headers["x-request-id"]
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_global_quota_and_window_reset() -> None:
    now = 0.0

    def clock() -> float:
        return now

    limiter = FixedWindowRateLimiter(
        per_client_limit=2, global_limit=2, window_seconds=60, clock=clock
    )
    assert (await limiter.check("a")).allowed
    assert (await limiter.check("b")).allowed
    assert not (await limiter.check("c")).allowed
    now = 61.0
    assert (await limiter.check("c")).allowed


@pytest.mark.asyncio
async def test_concurrency_limit_rejects_without_queueing() -> None:
    limiter = ConcurrencyLimiter(1)
    assert await limiter.acquire()
    assert not await limiter.acquire()
    await limiter.release()
    assert await limiter.acquire()


def test_oversized_payload_is_rejected_before_validation() -> None:
    settings = Settings(environment="test", log_level="WARNING", max_request_body_bytes=1_024)
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/v1/chat",
            content=b"x" * 1_025,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "Request payload is too large.",
    }


def test_request_wall_clock_timeout_is_safe() -> None:
    class SlowRepository:
        async def metadata(self):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.1)

    settings = Settings(environment="test", log_level="WARNING", request_timeout_seconds=0.01)
    with TestClient(create_app(settings=settings, repository=SlowRepository())) as client:
        response = client.get("/api/v1/metadata")

    assert response.status_code == 504
    assert response.json()["error"] == {
        "code": "REQUEST_TIMEOUT",
        "message": "Request processing timed out.",
    }


def test_cors_is_allowlisted_and_wildcard_is_rejected() -> None:
    settings = Settings(environment="test", cors_origins="https://ui.example")
    with TestClient(create_app(settings=settings)) as client:
        allowed = client.options(
            "/api/v1/metadata",
            headers={
                "origin": "https://ui.example",
                "access-control-request-method": "GET",
            },
        )
        denied = client.options(
            "/api/v1/metadata",
            headers={
                "origin": "https://evil.example",
                "access-control-request-method": "GET",
            },
        )

    assert allowed.headers["access-control-allow-origin"] == "https://ui.example"
    assert "access-control-allow-origin" not in denied.headers
    with pytest.raises(ValueError, match="wildcard"):
        _ = Settings(cors_origins="*").parsed_cors_origins


def test_json_logging_redacts_credentials_and_content() -> None:
    record = logging.LogRecord(
        "security-test",
        logging.INFO,
        __file__,
        1,
        "authorization=Bearer top-secret token=abc123",
        (),
        None,
    )
    record.password = "database-secret"
    record.message_content = "private question"
    payload = json.loads(JsonFormatter().format(record))

    rendered = json.dumps(payload)
    assert "top-secret" not in rendered
    assert "abc123" not in rendered
    assert "database-secret" not in rendered
    assert "private question" not in rendered
    assert rendered.count("[REDACTED]") >= 4


def test_production_requires_client_id_salt() -> None:
    with pytest.raises(ValidationError, match="client_id_salt"):
        Settings(environment="production")

    assert Settings(environment="production", client_id_salt="server-secret")
