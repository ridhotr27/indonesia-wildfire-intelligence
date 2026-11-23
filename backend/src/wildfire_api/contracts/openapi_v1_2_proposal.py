"""Build the A03 OpenAPI proposal without changing the approved runtime app."""

from copy import deepcopy

from fastapi import FastAPI
from pydantic import create_model

from wildfire_api.contracts.api_v1_2_proposal import ChatResponseV1_2Proposal
from wildfire_api.main import create_app


def build_openapi_v1_2_proposal() -> dict[str, object]:
    document = deepcopy(create_app().openapi())
    proposed_chat_response = create_model(
        "ChatResponse",
        __base__=ChatResponseV1_2Proposal,
    )
    schema_app = FastAPI()

    @schema_app.get("/schema-only", response_model=proposed_chat_response)
    def schema_only() -> object:  # pragma: no cover - schema generation only
        raise NotImplementedError

    proposal_schemas = schema_app.openapi()["components"]["schemas"]
    components = document["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    schemas.update(proposal_schemas)
    info = document["info"]
    assert isinstance(info, dict)
    info["version"] = "1.2.0"
    info["description"] = (
        "A03 proposal only. Runtime remains on the approved v1.1.0 contract until "
        "explicit Tech Lead approval and coordinated B13/I05 implementation."
    )
    return document
