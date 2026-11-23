#!/usr/bin/env python3
"""Run LIR-11 failure injection only against process-owned loopback services."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from wildfire_api.core.errors import AppError
from wildfire_api.llm.ollama import LocalModelError, OllamaHttpClient
from wildfire_api.rag.persistence import PersistentIndexError, load_persistent_index
from wildfire_api.repositories.clickhouse import ClickHouseHttpQueryClient, QueryName


class _Server(ThreadingHTTPServer):
    daemon_threads = True


@contextmanager
def _failure_server(*, delay_seconds: float = 0) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if delay_seconds:
                time.sleep(delay_seconds)
            body = b'{"error":"isolated-lir11-failure"}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = _Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        if host != "127.0.0.1":
            raise RuntimeError("failure injection must bind loopback only")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


async def _clickhouse(url: str, timeout: float) -> dict[str, Any]:
    client = ClickHouseHttpQueryClient(
        url=url,
        database="lir11_isolated",
        username="lir11_reader",
        password="not-a-real-secret",
        timeout_seconds=timeout,
    )
    started = time.perf_counter()
    try:
        await client.query(QueryName.PROVINCES, {})
    except AppError as exc:
        return {
            "code": exc.code,
            "safe_message": exc.message,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    raise RuntimeError("ClickHouse failure injection unexpectedly succeeded")


def _ollama(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        OllamaHttpClient(url, timeout_seconds=timeout).post("/api/chat", {"model": "none"})
    except LocalModelError as exc:
        return {
            "code": "MODEL_UNAVAILABLE",
            "safe_message": str(exc),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    raise RuntimeError("Ollama failure injection unexpectedly succeeded")


def main() -> int:
    results: dict[str, Any] = {"environment": "process-owned-loopback-only"}
    with _failure_server() as url:
        results["clickhouse_connection"] = asyncio.run(_clickhouse(url, 0.2))
        results["ollama_connection"] = _ollama(url, 0.2)
    with _failure_server(delay_seconds=0.2) as url:
        results["clickhouse_timeout"] = asyncio.run(_clickhouse(url, 0.05))
        results["ollama_timeout"] = _ollama(url, 0.05)
    with TemporaryDirectory(prefix="lir11-qdrant-") as directory:
        try:
            load_persistent_index(storage_path=Path(directory) / "missing")
        except PersistentIndexError as exc:
            results["qdrant_missing"] = {"code": "INDEX_UNAVAILABLE", "safe_message": str(exc)}
        else:
            raise RuntimeError("Qdrant failure injection unexpectedly succeeded")
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
