import pytest
from pydantic import ValidationError

from wildfire_api.schemas.chat import ChatRequest
from wildfire_api.schemas.hotspots import SummaryRequest


def test_summary_rejects_reverse_date_range() -> None:
    with pytest.raises(ValidationError):
        SummaryRequest(
            product_id="MOCK_ONLY",
            province_codes=["MOCK-WEST"],
            date_from="2023-10-01",
            date_to="2023-09-01",
            group_by="month",
        )


def test_chat_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            message="Explain FRP",
            product_id="MOCK_ONLY",
            context={},
            unexpected=True,
        )


def test_chat_message_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 2_001, product_id="MOCK_ONLY", context={})
