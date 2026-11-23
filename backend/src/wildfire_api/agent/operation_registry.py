"""Read-only operation registry derived from the approved LIR-02 catalog."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import Field

from wildfire_api.agent.intent_models import FrozenStrictModel, OperationId

EXPECTED_CATALOG_VERSION = "hotspot-semantic-catalog-v1.0.0"
EXPECTED_SCHEMA_VERSION = "1.0.0"
EXPECTED_DATA_CONTRACT_VERSION = "1.0.0"


class CatalogCompatibilityError(RuntimeError):
    pass


class OperationDefinition(FrozenStrictModel):
    operation_id: OperationId
    route: Literal["analytics", "rag"]
    adapter_id: Literal[
        "hotspot_analytics_tool",
        "hotspot_province_analytics_tool",
        "nasa_retrieval_tool",
    ]
    required_slots: frozenset[str] = Field(default_factory=frozenset)
    forbidden_slots: frozenset[str] = Field(default_factory=frozenset)
    supported_dimensions: frozenset[str] = Field(default_factory=frozenset)


class OperationRegistry:
    def __init__(
        self,
        definitions: Mapping[OperationId, OperationDefinition],
        *,
        metric_id: str,
        product_id: str,
        province_codes: tuple[tuple[str, tuple[str, ...]], ...],
    ) -> None:
        self._definitions = MappingProxyType(dict(definitions))
        self.metric_id = metric_id
        self.product_id = product_id
        self.province_codes = province_codes

    def get(self, operation_id: OperationId) -> OperationDefinition:
        return self._definitions[operation_id]

    @property
    def definitions(self) -> Mapping[OperationId, OperationDefinition]:
        return self._definitions

    @classmethod
    def from_catalog(cls, path: Path | None = None) -> OperationRegistry:
        catalog_path = path or (
            Path(__file__).resolve().parents[4]
            / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if (
            catalog.get("catalog_version") != EXPECTED_CATALOG_VERSION
            or catalog.get("schema_version") != EXPECTED_SCHEMA_VERSION
            or catalog.get("data_contract_version") != EXPECTED_DATA_CONTRACT_VERSION
        ):
            raise CatalogCompatibilityError("unsupported semantic catalog version")

        catalog_operations = {item["id"]: item for item in catalog["operations"]}
        expected_analytics = set(catalog["metric"]["valid_operations"])
        if set(catalog_operations) != expected_analytics:
            raise CatalogCompatibilityError("semantic catalog operations are inconsistent")
        dimensions = frozenset(catalog["metric"]["valid_dimensions"])
        adapters = {
            "hotspot_summary_v1": "hotspot_analytics_tool",
            "hotspot_trend_v1": "hotspot_analytics_tool",
            "hotspot_multi_province_summary_v1": "hotspot_province_analytics_tool",
            "hotspot_province_ranking_v1": "hotspot_province_analytics_tool",
        }
        definitions: dict[OperationId, OperationDefinition] = {}
        for operation_id, adapter_id in adapters.items():
            item = catalog_operations[operation_id]
            definitions[operation_id] = OperationDefinition(
                operation_id=operation_id,
                route="analytics",
                adapter_id=adapter_id,
                required_slots=frozenset(item["required_slots"]),
                forbidden_slots=frozenset(item["forbidden_slots"]),
                supported_dimensions=dimensions,
            )
        definitions["nasa_documentation_v1"] = OperationDefinition(
            operation_id="nasa_documentation_v1",
            route="rag",
            adapter_id="nasa_retrieval_tool",
        )
        province_codes = tuple(
            (
                item["code"],
                tuple(
                    dict.fromkeys(
                        (
                            item["labels"]["id"],
                            item["labels"]["en"],
                            *(alias["text"] for alias in item["aliases"]),
                        )
                    )
                ),
            )
            for item in catalog["geography"]["provinces"]
        )
        return cls(
            definitions,
            metric_id=catalog["metric"]["id"],
            product_id=catalog["product"]["id"],
            province_codes=province_codes,
        )
