from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from wildfire_api.agent.runtime import AgentRuntime
from wildfire_api.agent.state import (
    AnalyticsToolInput,
    ProvinceAnalyticsToolInput,
    RetrievalToolInput,
    YearComparisonToolInput,
)
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.schemas.chat import ChatRequest, ChatResponse
from wildfire_api.schemas.hotspots import (
    SummaryRequest,
    SummaryResponse,
    YearComparisonRequest,
    YearComparisonResponse,
)
from wildfire_api.services.hotspots import HotspotService

logger = logging.getLogger("wildfire_api.agent")


class PassageRetriever(Protocol):
    def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievedPassage]: ...


class HotspotAnalyticsTool:
    """Typed adapter; there is deliberately no SQL argument or query-text seam."""

    def __init__(self, hotspot_service: HotspotService) -> None:
        self._hotspot_service = hotspot_service

    async def __call__(self, tool_input: AnalyticsToolInput, request_id: str) -> SummaryResponse:
        return await self._hotspot_service.summary(
            SummaryRequest(
                product_id=tool_input.product_id,
                province_codes=[tool_input.province_code],
                date_from=tool_input.date_from,
                date_to=tool_input.date_to,
                group_by="month",
            ),
            request_id,
        )


class HotspotProvinceAnalyticsTool:
    def __init__(self, hotspot_service: HotspotService) -> None:
        self._hotspot_service = hotspot_service

    async def __call__(self, tool_input: ProvinceAnalyticsToolInput, request_id: str):
        return await self._hotspot_service.province_analytics(
            product_id=tool_input.product_id,
            province_codes=tool_input.province_codes,
            date_from=tool_input.date_from,
            date_to=tool_input.date_to,
            ranking=tool_input.operation == "ranking",
            direction=tool_input.direction,
            top_n=tool_input.top_n,
            comparison_requested=tool_input.comparison_requested,
        )


class HotspotYearComparisonTool:
    def __init__(self, hotspot_service: HotspotService) -> None:
        self._hotspot_service = hotspot_service

    async def __call__(
        self, tool_input: YearComparisonToolInput, request_id: str
    ) -> YearComparisonResponse:
        return await self._hotspot_service.year_comparison(
            YearComparisonRequest(
                product_id=tool_input.product_id,
                province_code=tool_input.province_code,
                years=list(tool_input.years),
            ),
            request_id,
        )


class NasaRetrievalTool:
    def __init__(self, retriever: PassageRetriever) -> None:
        self._retriever = retriever

    async def __call__(self, tool_input: RetrievalToolInput) -> list[RetrievedPassage]:
        # Qdrant's local client is synchronous; keep it off the event-loop thread.
        return await asyncio.to_thread(
            self._retriever.retrieve, tool_input.query, limit=tool_input.limit
        )


class ChatService:
    def __init__(self, runtime: AgentRuntime, hotspot_service: HotspotService) -> None:
        self._runtime = runtime
        self._hotspot_service = hotspot_service

    async def respond(self, request: ChatRequest, request_id: str) -> ChatResponse:
        await self._hotspot_service.validate_product(request.product_id)
        state = await self._runtime.invoke(
            {
                "request_id": request_id,
                "message": request.message,
                "product_id": request.product_id,
                "province_code": request.context.province_code,
                "date_from": request.context.date_from,
                "date_to": request.context.date_to,
            }
        )
        response = ChatResponse.model_validate(state["response"])
        logger.info(
            "agent_complete",
            extra={
                "request_id": request_id,
                "tool_type": state.get("mode", "unsupported"),
                "graph_steps": state.get("graph_steps", 0),
                "tool_calls": state.get("tool_calls", 0),
                "llm_calls": response.usage.llm_calls,
                "token_usage": 0,
                "estimated_cost_usd": 0,
                "result_size": len(response.model_dump_json()),
                "dependency_status": "ok",
            },
        )
        return response
