from wildfire_api.schemas.chat import ChatRequest, ChatResponse
from wildfire_api.schemas.common import ErrorResponse
from wildfire_api.schemas.hotspots import (
    GeoJsonQuery,
    GeoJsonResponse,
    SummaryRequest,
    SummaryResponse,
)
from wildfire_api.schemas.metadata import MetadataResponse

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ErrorResponse",
    "GeoJsonQuery",
    "GeoJsonResponse",
    "MetadataResponse",
    "SummaryRequest",
    "SummaryResponse",
]
