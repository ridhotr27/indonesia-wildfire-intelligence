"""Bounded current-turn/UI context and semantics-preserving RAG rewrites."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import Field

from wildfire_api.agent.filter_resolver import ChatFilterResolver
from wildfire_api.agent.intent_models import FrozenStrictModel, IntentPlan

ContextStatus = Literal["resolved", "needs_clarification", "invalid"]

_FOLLOW_UP = re.compile(
    r"^\s*(?:and\b|also\b|what about\b|how about\b|then\b|"
    r"dan\b|lalu\b|bagaimana dengan\b|kalau\b)",
    re.IGNORECASE,
)
_SEMANTIC_ANCHOR = re.compile(
    r"\b(?:hotspots?|detections?|count|trend|rank|highest|lowest|more|less|"
    r"firms|viirs|frp|confidence|satellite|confirmed fires?|burned area|"
    r"deteksi|jumlah|tren|peringkat|terbanyak|terendah|satelit|kebakaran)\b",
    re.IGNORECASE,
)
_UNBOUND_REFERENCE = re.compile(r"\b(?:there|that|those|it|di sana|itu|tersebut)\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|without|isn t|aren t|bukan|tidak|jangan)\b", re.I)
_PRODUCT_TERMS = re.compile(r"\b(?:viirs|modis|noaa-?20|vnp14img|suomi npp)\b", re.I)
_UNSUPPORTED_MEASURES = re.compile(
    r"\b(?:burned area|confirmed fires?|cause|forecast|severity|"
    r"luas terbakar|kebakaran terkonfirmasi|penyebab|prediksi)\b",
    re.I,
)
_COMPARISON = re.compile(
    r"\b(?:compare|comparison|versus|difference|which had|more|less|"
    r"bandingkan|mana yang|lebih banyak|lebih sedikit)\b",
    re.I,
)
_WORDS = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "apa",
    "apakah",
    "are",
    "bagaimana",
    "dan",
    "di",
    "does",
    "how",
    "in",
    "is",
    "itu",
    "of",
    "the",
    "what",
    "yang",
}


def _normalize(value: str) -> str:
    return " ".join(
        _WORDS.findall(unicodedata.normalize("NFKC", value).casefold().replace("'", " "))
    )


class ResolvedConversationContext(FrozenStrictModel):
    original_message: str = Field(min_length=1, max_length=2_000)
    message_province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    province_source: Literal["message", "ui_context", "absent"]
    date_from: date | None = None
    date_to: date | None = None
    date_source: Literal["message", "ui_context", "absent"]
    follow_up_frame: bool
    status: ContextStatus
    clarification_codes: tuple[str, ...] = Field(default=(), max_length=6)


class RewriteValidation(FrozenStrictModel):
    accepted: bool
    query: str | None = Field(default=None, min_length=1, max_length=500)
    reason: Literal[
        "accepted",
        "ambiguous_reference",
        "added_entity",
        "dropped_entity",
        "changed_negation",
        "changed_measurement",
        "topic_mismatch",
        "invalid_length",
    ]


class ContextResolutionError(ValueError):
    pass


class ConversationContextResolver:
    def __init__(self, filter_resolver: ChatFilterResolver | None = None) -> None:
        self._filters = filter_resolver or ChatFilterResolver()

    def resolve(
        self,
        message: str,
        *,
        province_code: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> ResolvedConversationContext:
        if not 1 <= len(message) <= 2_000:
            raise ContextResolutionError("message must contain 1-2000 characters")
        message_only = self._filters.resolve(
            message, province_code=None, date_from=None, date_to=None
        )
        resolved = self._filters.resolve(
            message,
            province_code=province_code,
            date_from=date_from,
            date_to=date_to,
        )
        normalized = _normalize(message)
        follow_up = bool(_FOLLOW_UP.search(normalized))
        unresolved_reference = bool(_UNBOUND_REFERENCE.search(normalized)) and not (
            message_only.province_codes or _SEMANTIC_ANCHOR.search(normalized)
        )
        missing_frame = follow_up and not _SEMANTIC_ANCHOR.search(normalized)
        codes = list(resolved.codes)
        status: ContextStatus = resolved.status
        if missing_frame or unresolved_reference:
            status = "needs_clarification"
            codes = ["ambiguous_reference"]
        return ResolvedConversationContext(
            original_message=message,
            message_province_codes=message_only.province_codes,
            province_codes=resolved.province_codes,
            province_source=resolved.province_source.value,
            date_from=resolved.date_from,
            date_to=resolved.date_to,
            date_source=resolved.date_source.value,
            follow_up_frame=follow_up,
            status=status,
            clarification_codes=tuple(dict.fromkeys(codes)),
        )


class PlanContextValidator:
    """Verify planner provenance against canonical current/UI context."""

    def validate(
        self,
        plan: IntentPlan,
        context: ResolvedConversationContext,
        *,
        ui_product_id: str,
        ui_province_code: str | None,
        ui_date_from: date | None,
        ui_date_to: date | None,
    ) -> None:
        if context.status == "invalid" and plan.route in {"analytics", "combined"}:
            raise ContextResolutionError("invalid context cannot authorize analytics")
        if context.status == "needs_clarification" and plan.route in {"analytics", "combined"}:
            blocking = set(context.clarification_codes)
            analytics_operations = {
                operation
                for operation in plan.operation_ids
                if operation != "nasa_documentation_v1"
            }
            if blocking == {"missing_province"} and analytics_operations == {
                "hotspot_province_ranking_v1"
            }:
                blocking.clear()
            if blocking:
                raise ContextResolutionError("unresolved context cannot authorize analytics")
        message = _normalize(context.original_message)
        for entity in plan.entities:
            value = str(entity.value)
            if entity.kind == "province_code":
                if entity.source == "current_message":
                    allowed = context.message_province_codes
                else:
                    allowed = (
                        (ui_province_code,)
                        if ui_province_code and context.province_source == "ui_context"
                        else ()
                    )
                if value not in allowed:
                    raise ContextResolutionError("province provenance is not supported")
            elif entity.kind in {"date_from", "date_to"}:
                expected = context.date_from if entity.kind == "date_from" else context.date_to
                ui_expected = ui_date_from if entity.kind == "date_from" else ui_date_to
                if entity.source == "current_message" and context.date_source != "message":
                    raise ContextResolutionError("date provenance is not supported")
                if entity.source == "ui_context" and (
                    context.date_source != "ui_context" or value != str(ui_expected)
                ):
                    raise ContextResolutionError("date provenance is not supported")
                if value != str(expected):
                    raise ContextResolutionError("date differs from canonical context")
            elif entity.kind == "product_id":
                if entity.source == "ui_context" and value != ui_product_id:
                    raise ContextResolutionError("product provenance is not supported")
                if entity.source == "current_message" and not _PRODUCT_TERMS.search(message):
                    raise ContextResolutionError("product provenance is not supported")
            elif entity.kind == "metric_id" and entity.source == "current_message":
                if not re.search(r"\b(?:hotspots?|detections?|deteksi|jumlah hotspot)\b", message):
                    raise ContextResolutionError("metric provenance is not supported")
            elif entity.kind == "metric_id":
                raise ContextResolutionError("metric provenance is not supported")
            elif entity.source == "ui_context":
                raise ContextResolutionError(f"{entity.kind} is not supplied by UI context")
            elif entity.kind == "direction":
                patterns = {
                    "highest": r"\b(?:highest|most|top|terbanyak|teratas)\b",
                    "lowest": r"\b(?:lowest|least|bottom|terendah|tersedikit)\b",
                }
                if value not in patterns or not re.search(patterns[value], message):
                    raise ContextResolutionError("direction provenance is not supported")
            elif entity.kind == "top_n":
                if not re.search(rf"\b{re.escape(value)}\b", message):
                    raise ContextResolutionError("ranking limit provenance is not supported")
            elif entity.kind == "ranking_selection":
                if value != "top_n" or not re.search(
                    r"\b(?:top|bottom|highest|lowest|teratas|terendah)\b", message
                ):
                    raise ContextResolutionError("ranking selection provenance is not supported")
            elif entity.kind == "comparison_requested":
                if bool(entity.value) != bool(_COMPARISON.search(message)):
                    raise ContextResolutionError("comparison provenance is not supported")
            elif entity.kind == "dimension":
                dimension_patterns = {
                    "month_utc": r"\b(?:month|monthly|bulan|bulanan)\b",
                    "date_utc": r"\b(?:day|daily|date|hari|harian|tanggal)\b",
                    "province_code": r"\b(?:province|provinsi)\b",
                    "product_id": r"\b(?:product|produk|viirs|modis|vnp14img)\b",
                }
                if value not in dimension_patterns or not re.search(
                    dimension_patterns[value], message
                ):
                    raise ContextResolutionError("dimension provenance is not supported")


class RetrievalRewriteValidator:
    """Conservatively validate a derived NASA retrieval query."""

    def __init__(self, filter_resolver: ChatFilterResolver | None = None) -> None:
        self._filters = filter_resolver or ChatFilterResolver()

    def validate(
        self,
        original: str,
        rewritten: str,
        context: ResolvedConversationContext,
    ) -> RewriteValidation:
        if not 1 <= len(rewritten) <= 500:
            return RewriteValidation(accepted=False, reason="invalid_length")
        if context.status == "needs_clarification" and context.follow_up_frame:
            return RewriteValidation(accepted=False, reason="ambiguous_reference")
        original_filters = self._filters.resolve(
            original, province_code=None, date_from=None, date_to=None
        )
        rewritten_filters = self._filters.resolve(
            rewritten, province_code=None, date_from=None, date_to=None
        )
        original_provinces = set(original_filters.province_codes)
        rewritten_provinces = set(rewritten_filters.province_codes)
        allowed_provinces = set(context.province_codes)
        if rewritten_provinces - allowed_provinces:
            return RewriteValidation(accepted=False, reason="added_entity")
        if original_provinces - rewritten_provinces:
            return RewriteValidation(accepted=False, reason="dropped_entity")
        original_normalized = _normalize(original)
        rewritten_normalized = _normalize(rewritten)
        if bool(_NEGATION.search(original_normalized)) != bool(
            _NEGATION.search(rewritten_normalized)
        ):
            return RewriteValidation(accepted=False, reason="changed_negation")
        original_products = set(_PRODUCT_TERMS.findall(original_normalized))
        rewritten_products = set(_PRODUCT_TERMS.findall(rewritten_normalized))
        if rewritten_products - original_products:
            return RewriteValidation(accepted=False, reason="added_entity")
        if original_products - rewritten_products:
            return RewriteValidation(accepted=False, reason="dropped_entity")
        original_measures = set(_UNSUPPORTED_MEASURES.findall(original_normalized))
        rewritten_measures = set(_UNSUPPORTED_MEASURES.findall(rewritten_normalized))
        if original_measures != rewritten_measures:
            return RewriteValidation(accepted=False, reason="changed_measurement")
        original_numbers = set(re.findall(r"\b\d+\b", original_normalized))
        rewritten_numbers = set(re.findall(r"\b\d+\b", rewritten_normalized))
        if rewritten_numbers - original_numbers:
            return RewriteValidation(accepted=False, reason="added_entity")
        if original_numbers - rewritten_numbers:
            return RewriteValidation(accepted=False, reason="dropped_entity")
        original_dates = (original_filters.date_from, original_filters.date_to)
        rewritten_dates = (rewritten_filters.date_from, rewritten_filters.date_to)
        if original_dates != rewritten_dates:
            reason = (
                "dropped_entity"
                if any(original_dates) and not any(rewritten_dates)
                else "added_entity"
            )
            return RewriteValidation(accepted=False, reason=reason)
        original_terms = set(_WORDS.findall(original_normalized)) - _STOPWORDS
        rewritten_terms = set(_WORDS.findall(rewritten_normalized)) - _STOPWORDS
        if not original_terms & rewritten_terms:
            return RewriteValidation(accepted=False, reason="topic_mismatch")
        return RewriteValidation(accepted=True, query=rewritten.strip(), reason="accepted")
