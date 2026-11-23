from typing import Annotated

from fastapi import Depends, Request

from wildfire_api.services.chat import ChatService
from wildfire_api.services.hotspots import HotspotService


def get_hotspot_service(request: Request) -> HotspotService:
    return request.app.state.hotspot_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


HotspotServiceDependency = Annotated[HotspotService, Depends(get_hotspot_service)]
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
