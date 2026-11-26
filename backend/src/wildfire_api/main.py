import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from wildfire_api.agent.runtime import AgentLimits, BoundedLangGraphRuntime
from wildfire_api.agent.semantic_intent import (
    SemanticIntentError,
    SemanticIntentIndex,
    load_semantic_intent_index,
)
from wildfire_api.agent.semantic_planner import GuardedSemanticPlanner
from wildfire_api.api.router import api_router
from wildfire_api.core.config import Settings, get_settings
from wildfire_api.core.errors import AppError
from wildfire_api.core.logging import configure_logging
from wildfire_api.core.request_context import request_id_context
from wildfire_api.core.security import (
    ConcurrencyLimiter,
    FixedWindowRateLimiter,
    RequestBodyLimitMiddleware,
    RequestTimeoutMiddleware,
    pseudonymous_client_id,
)
from wildfire_api.llm.ollama import OllamaAnswerGenerator, OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.extractive import ExtractiveAnswerGenerator
from wildfire_api.rag.persistence import load_persistent_index
from wildfire_api.repositories.clickhouse import (
    ClickHouseHotspotRepository,
    ClickHouseHttpQueryClient,
)
from wildfire_api.repositories.hotspots import HotspotRepository
from wildfire_api.repositories.mock import MockHotspotRepository
from wildfire_api.services.chat import (
    ChatService,
    HotspotAnalyticsTool,
    HotspotProvinceAnalyticsTool,
    HotspotYearComparisonTool,
    NasaRetrievalTool,
    PassageRetriever,
)
from wildfire_api.services.hotspots import HotspotService

logger = logging.getLogger("wildfire_api.requests")


def _configured_repository(settings: Settings) -> HotspotRepository:
    if settings.analytics_backend == "mock":
        return MockHotspotRepository()
    return ClickHouseHotspotRepository(
        ClickHouseHttpQueryClient(
            url=settings.clickhouse_url,
            database=settings.clickhouse_database,
            username=settings.clickhouse_username,
            password=settings.clickhouse_password.get_secret_value(),
            timeout_seconds=settings.clickhouse_timeout_seconds,
        )
    )


def _error_response(
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    error: dict[str, str | int] = {"code": code, "message": message}
    headers: dict[str, str] = {}
    if retry_after_seconds is not None:
        error["retry_after_seconds"] = retry_after_seconds
        headers["Retry-After"] = str(retry_after_seconds)
    return JSONResponse(
        status_code=status_code,
        content={"request_id": request_id, "error": error},
        headers=headers,
    )


def create_app(
    settings: Settings | None = None,
    repository: HotspotRepository | None = None,
    rag_retriever: PassageRetriever | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    hotspot_service = HotspotService(
        repository or _configured_repository(settings),
        max_date_range_days=settings.max_date_range_days,
        max_features=settings.max_geojson_features,
    )
    ollama_client = OllamaHttpClient(
        settings.ollama_base_url,
        settings.ollama_timeout_seconds,
        allow_internal_service=settings.ollama_internal_service,
    )
    answer_generator = (
        ExtractiveAnswerGenerator()
        if settings.agent_model_provider == "extractive"
        else OllamaAnswerGenerator(
            client=ollama_client,
            model=settings.agent_model_name,
            max_tokens=settings.agent_max_model_tokens,
        )
        if settings.agent_model_provider == "ollama"
        else None
    )
    embeddings = (
        OllamaEmbeddings(client=ollama_client, model=settings.embedding_model_name)
        if settings.embedding_provider == "ollama"
        else None
    )
    semantic_embeddings = (
        OllamaEmbeddings(client=ollama_client, model=settings.embedding_model_name)
        if settings.semantic_routing_mode != "disabled"
        else None
    )

    def chat_service(
        retriever: PassageRetriever | None,
        intent_index: SemanticIntentIndex | None = None,
    ) -> ChatService:
        return ChatService(
            BoundedLangGraphRuntime(
                analytics_tool=HotspotAnalyticsTool(hotspot_service),
                province_analytics_tool=HotspotProvinceAnalyticsTool(hotspot_service),
                year_comparison_tool=HotspotYearComparisonTool(hotspot_service),
                retrieval_tool=NasaRetrievalTool(retriever) if retriever else None,
                planner=(
                    GuardedSemanticPlanner(intent_index, mode=settings.semantic_routing_mode)
                    if intent_index is not None
                    else None
                ),
                limits=AgentLimits(
                    max_graph_steps=settings.agent_max_graph_steps,
                    max_tool_calls=settings.agent_max_tool_calls,
                    timeout_seconds=settings.agent_timeout_seconds,
                    combined_stage_budgeting=settings.agent_combined_stage_budgeting,
                    max_retrieved_characters=settings.agent_max_retrieved_characters,
                    max_model_tokens=settings.agent_max_model_tokens,
                ),
                answer_generator=answer_generator,
                embedding_model=(
                    settings.embedding_model_name
                    if settings.embedding_provider == "ollama"
                    else "local-hashing-v1"
                ),
                retrieval_collection=settings.qdrant_collection,
                generation_model=settings.agent_model_name,
            ),
            hotspot_service,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        configured_retriever = rag_retriever
        owns_retriever = False
        intent_index: SemanticIntentIndex | None = None
        if configured_retriever is None and settings.rag_backend == "local":
            configured_retriever = load_persistent_index(
                storage_path=settings.qdrant_path,
                collection_name=settings.qdrant_collection,
                embeddings=embeddings,
                expected_embedding_name=(
                    f"ollama:{settings.embedding_model_name}"
                    if embeddings is not None
                    else "local-hashing-v1"
                ),
                retrieval_profile=settings.rag_retrieval_profile,
                expected_chunking_profile=settings.rag_chunking_profile,
            )
            owns_retriever = True
        if settings.semantic_routing_mode != "disabled":
            if semantic_embeddings is None:
                raise RuntimeError("semantic routing requires configured local embeddings")
            try:
                intent_index = load_semantic_intent_index(
                    storage_path=settings.semantic_intent_path,
                    collection_name=settings.semantic_intent_collection,
                    embeddings=semantic_embeddings,
                    expected_embedding_name=f"ollama:{settings.embedding_model_name}",
                    require_calibrated=settings.semantic_routing_mode == "guarded",
                )
            except SemanticIntentError as exc:
                logger.warning(
                    "semantic_intent_degraded",
                    extra={"dependency_status": "unavailable", "reason": str(exc)},
                )
        app.state.chat_service = chat_service(configured_retriever, intent_index)
        try:
            yield
        finally:
            close = getattr(configured_retriever, "close", None) if owns_retriever else None
            if close is not None:
                close()
            if intent_index is not None:
                intent_index.close()

    app = FastAPI(
        title=settings.app_name,
        version="1.2.0",
        description=(
            "Historical hotspot exploration API. Current default data is an explicitly "
            "synthetic mock; approved real-data integration remains gated behind later tickets."
        ),
        lifespan=lifespan,
    )
    app.state.hotspot_service = hotspot_service
    app.state.chat_service = chat_service(rag_retriever)
    rate_limiter = FixedWindowRateLimiter(
        per_client_limit=settings.per_client_requests_per_minute,
        global_limit=settings.global_requests_per_minute,
    )
    concurrency_limiter = ConcurrencyLimiter(settings.max_concurrent_requests)

    if settings.parsed_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.parsed_cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
    )
    app.add_middleware(
        RequestTimeoutMiddleware,
        timeout_seconds=settings.request_timeout_seconds,
        health_path=f"{settings.api_prefix}/health",
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid4())
        token = request_id_context.set(request_id)
        started = perf_counter()
        status_code = 500
        client_id = pseudonymous_client_id(request, settings.client_id_salt.get_secret_value())
        acquired = False
        try:
            if request.url.path != f"{settings.api_prefix}/health":
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = settings.max_request_body_bytes + 1
                    if declared_size > settings.max_request_body_bytes:
                        response = _error_response(
                            request_id,
                            "VALIDATION_ERROR",
                            "Request payload is too large.",
                            413,
                        )
                        status_code = response.status_code
                        response.headers["X-Request-ID"] = request_id
                        return response
                decision = await rate_limiter.check(client_id)
                if not decision.allowed:
                    response = _error_response(
                        request_id,
                        "RATE_LIMITED",
                        "Request quota reached.",
                        429,
                        decision.retry_after_seconds,
                    )
                    status_code = response.status_code
                    response.headers["X-Request-ID"] = request_id
                    return response
                acquired = await concurrency_limiter.acquire()
                if not acquired:
                    response = _error_response(
                        request_id,
                        "RATE_LIMITED",
                        "Server concurrency limit reached.",
                        429,
                        1,
                    )
                    status_code = response.status_code
                    response.headers["X-Request-ID"] = request_id
                    return response
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            if acquired:
                await concurrency_limiter.release()
            logger.info(
                "request_complete",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "route": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "client_id": client_id,
                    "dependency_status": "unavailable" if status_code == 503 else "ok",
                },
            )
            request_id_context.reset(token)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            request_id_context.get() or "unknown",
            exc.code,
            exc.message,
            exc.status_code,
            exc.retry_after_seconds,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info(
            "request_validation_failed",
            extra={
                "request_id": request_id_context.get() or "unknown",
                "error_count": len(exc.errors()),
            },
        )
        return _error_response(
            request_id_context.get() or "unknown",
            "VALIDATION_ERROR",
            "Request validation failed.",
            422,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = "Resource not found." if exc.status_code == 404 else str(exc.detail)
        return _error_response(
            request_id_context.get() or "unknown", code, message, exc.status_code
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            extra={
                "request_id": request_id_context.get() or "unknown",
                "exception_class": type(exc).__name__,
            },
        )
        return _error_response(
            request_id_context.get() or "unknown",
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            500,
        )

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
