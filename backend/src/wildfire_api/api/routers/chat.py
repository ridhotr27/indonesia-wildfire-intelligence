from fastapi import APIRouter

from wildfire_api.api.dependencies import ChatServiceDependency
from wildfire_api.core.request_context import get_request_id
from wildfire_api.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, service: ChatServiceDependency) -> ChatResponse:
    return await service.respond(payload, get_request_id())
