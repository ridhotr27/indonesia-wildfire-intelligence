from wildfire_api.schemas.common import ErrorResponse

ERROR_RESPONSES: dict[int, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Invalid filter combination"},
    404: {"model": ErrorResponse, "description": "No data or resource not found"},
    422: {"model": ErrorResponse, "description": "Malformed input"},
    429: {"model": ErrorResponse, "description": "Request quota reached"},
    503: {"model": ErrorResponse, "description": "Required dependency unavailable"},
    504: {"model": ErrorResponse, "description": "Bounded processing time exceeded"},
}
