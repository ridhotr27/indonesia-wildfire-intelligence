from fastapi import APIRouter

from wildfire_api.api.dependencies import HotspotServiceDependency
from wildfire_api.core.request_context import get_request_id
from wildfire_api.schemas.metadata import MetadataResponse

router = APIRouter(tags=["metadata"])


@router.get("/metadata", response_model=MetadataResponse)
async def metadata(service: HotspotServiceDependency) -> MetadataResponse:
    return await service.metadata(get_request_id())
