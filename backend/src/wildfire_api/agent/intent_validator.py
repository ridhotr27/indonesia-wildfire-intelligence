"""Fail-closed validation from an untrusted IntentPlan to typed operations."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from wildfire_api.agent.intent_models import (
    IntentPlan,
    OperationArguments,
    ValidatedOperation,
    ValidatedPlan,
)
from wildfire_api.agent.operation_registry import OperationRegistry

RejectionCode = Literal[
    "non_executable_route",
    "deterministic_denial",
    "duplicate_entity",
    "missing_slot",
    "forbidden_slot",
    "invalid_metric",
    "invalid_product",
    "invalid_province",
    "invalid_date",
    "invalid_dimension",
    "invalid_operator",
    "incompatible_operation",
]


class IntentPlanRejected(ValueError):
    def __init__(self, code: RejectionCode, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class IntentPlanValidator:
    def __init__(self, registry: OperationRegistry, catalog_path: Path | None = None) -> None:
        path = catalog_path or (
            Path(__file__).resolve().parents[4]
            / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"
        )
        self._catalog = json.loads(path.read_text(encoding="utf-8"))
        self._registry = registry
        self._metric = self._catalog["metric"]["id"]
        self._product = self._catalog["product"]["id"]
        self._provinces = {item["code"] for item in self._catalog["geography"]["provinces"]}
        self._dimensions = set(self._catalog["metric"]["valid_dimensions"])
        bounds = self._catalog["coverage"]["date_bounds"]
        self._date_from = date.fromisoformat(bounds["from"])
        self._date_to = date.fromisoformat(bounds["to"])

    def validate(self, plan: IntentPlan, *, deterministic_denied: bool = False) -> ValidatedPlan:
        if deterministic_denied:
            raise IntentPlanRejected(
                "deterministic_denial", "deterministic policy denied execution"
            )
        if plan.route in {"clarification", "unsupported"}:
            raise IntentPlanRejected("non_executable_route", "plan does not authorize execution")

        values: dict[str, list[Any]] = {}
        for entity in plan.entities:
            values.setdefault(entity.kind, []).append(entity.value)
        singletons = set(values) - {"province_code", "dimension"}
        if any(len(values[kind]) != 1 for kind in singletons):
            raise IntentPlanRejected("duplicate_entity", "singleton entity was repeated")

        operations: list[ValidatedOperation] = []
        for operation_id in plan.operation_ids:
            definition = self._registry.get(operation_id)
            if operation_id == "nasa_documentation_v1":
                operations.append(
                    ValidatedOperation(
                        operation_id=operation_id,
                        adapter_id=definition.adapter_id,
                        arguments=None,
                        retrieval_query=plan.retrieval_query,
                    )
                )
                continue
            arguments = self._analytics_arguments(operation_id, values)
            operations.append(
                ValidatedOperation(
                    operation_id=operation_id,
                    adapter_id=definition.adapter_id,
                    arguments=arguments,
                )
            )
        return ValidatedPlan(route=plan.route, operations=tuple(operations))

    def _analytics_arguments(
        self, operation_id: str, values: dict[str, list[Any]]
    ) -> OperationArguments:
        required = {"metric_id", "product_id", "date_from", "date_to"}
        if operation_id != "hotspot_province_ranking_v1":
            required.add("province_code")
        missing = sorted(required - values.keys())
        if missing:
            raise IntentPlanRejected(
                "missing_slot", f"missing required slots: {', '.join(missing)}"
            )

        metric = self._string(values, "metric_id")
        product = self._string(values, "product_id")
        if metric != self._metric:
            raise IntentPlanRejected("invalid_metric", "metric is not approved")
        if product != self._product:
            raise IntentPlanRejected("invalid_product", "product is not approved")
        provinces = tuple(str(value) for value in values.get("province_code", []))
        if len(provinces) != len(set(provinces)):
            raise IntentPlanRejected("duplicate_entity", "province codes must be distinct")
        if any(code not in self._provinces for code in provinces):
            raise IntentPlanRejected("invalid_province", "province code is not approved")
        dimensions = tuple(str(value) for value in values.get("dimension", []))
        if len(dimensions) != len(set(dimensions)) or any(
            dimension not in self._dimensions for dimension in dimensions
        ):
            raise IntentPlanRejected("invalid_dimension", "dimension is not approved")

        start = self._parse_date(values, "date_from")
        end = self._parse_date(values, "date_to")
        if start > end or start < self._date_from or end > self._date_to:
            raise IntentPlanRejected("invalid_date", "date range is invalid or outside coverage")

        direction = self._optional_string(values, "direction")
        selection = self._optional_string(values, "ranking_selection")
        top_n = self._optional_int(values, "top_n")
        comparison = self._optional_bool(values, "comparison_requested")
        if operation_id in {"hotspot_summary_v1", "hotspot_trend_v1"}:
            if len(provinces) != 1:
                raise IntentPlanRejected(
                    "incompatible_operation", "operation requires one province"
                )
            if any(value is not None for value in (direction, selection, top_n, comparison)):
                raise IntentPlanRejected("forbidden_slot", "operation contains incompatible slots")
        elif operation_id == "hotspot_multi_province_summary_v1":
            if not 2 <= len(provinces) <= 38:
                raise IntentPlanRejected(
                    "incompatible_operation", "operation requires 2-38 provinces"
                )
            if any(value is not None for value in (direction, selection, top_n)):
                raise IntentPlanRejected("forbidden_slot", "multi-province operation cannot rank")
        elif operation_id == "hotspot_province_ranking_v1":
            if provinces:
                raise IntentPlanRejected(
                    "forbidden_slot", "ranking operates on the province universe"
                )
            if direction not in {"highest", "lowest"} or selection != "top_n" or top_n is None:
                raise IntentPlanRejected("invalid_operator", "ranking requires direction and top_n")
            if comparison is not None:
                raise IntentPlanRejected("forbidden_slot", "ranking cannot request comparison")

        return OperationArguments(
            metric_id=metric,
            product_id=product,
            province_codes=provinces,
            date_from=start,
            date_to=end,
            dimensions=dimensions,
            direction=direction,
            ranking_selection=selection,
            top_n=top_n,
            comparison_requested=comparison,
        )

    @staticmethod
    def _string(values: dict[str, list[Any]], key: str) -> str:
        value = values[key][0]
        if not isinstance(value, str):
            raise IntentPlanRejected("incompatible_operation", f"{key} must be a string")
        return value

    @classmethod
    def _optional_string(cls, values: dict[str, list[Any]], key: str) -> str | None:
        return cls._string(values, key) if key in values else None

    @staticmethod
    def _optional_int(values: dict[str, list[Any]], key: str) -> int | None:
        if key not in values:
            return None
        value = values[key][0]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 38:
            raise IntentPlanRejected("invalid_operator", f"{key} must be between 1 and 38")
        return value

    @staticmethod
    def _optional_bool(values: dict[str, list[Any]], key: str) -> bool | None:
        if key not in values:
            return None
        value = values[key][0]
        if not isinstance(value, bool):
            raise IntentPlanRejected("incompatible_operation", f"{key} must be boolean")
        return value

    @classmethod
    def _parse_date(cls, values: dict[str, list[Any]], key: str) -> date:
        try:
            return date.fromisoformat(cls._string(values, key))
        except ValueError as exc:
            raise IntentPlanRejected("invalid_date", f"{key} must be an ISO date") from exc
