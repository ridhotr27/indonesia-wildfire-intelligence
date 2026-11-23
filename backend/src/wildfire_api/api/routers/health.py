from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from wildfire_api.core.request_context import get_request_id


class HealthResponse(BaseModel):
    request_id: str
    status: Literal["ok"]
    api_version: Literal["1.0.0"] = "1.0.0"


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(request_id=get_request_id(), status="ok")
