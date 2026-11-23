from fastapi import APIRouter

from wildfire_api.api.responses import ERROR_RESPONSES
from wildfire_api.api.routers import chat, health, hotspots, metadata

api_router = APIRouter(responses=ERROR_RESPONSES)
api_router.include_router(health.router)
api_router.include_router(metadata.router)
api_router.include_router(hotspots.router)
api_router.include_router(chat.router)
