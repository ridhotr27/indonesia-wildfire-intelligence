from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FilterSource(StrEnum):
    MESSAGE = "message"
    UI_CONTEXT = "ui_context"
    ABSENT = "absent"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NEEDS_CLARIFICATION = "needs_clarification"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class ResolvedChatContext(BaseModel):
    """Internal, immutable filter result. It is never serialized into API v1 responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    province_code: str | None = None
    province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    date_from: date | None = None
    date_to: date | None = None
    comparison_years: tuple[int, ...] = Field(default=(), min_length=0, max_length=3)
    province_source: FilterSource = FilterSource.ABSENT
    date_source: FilterSource = FilterSource.ABSENT
    mention_labels: tuple[str, ...] = Field(default=(), max_length=4)
    codes: tuple[str, ...] = Field(default=(), max_length=4)
    status: ResolutionStatus


# D04's 38 canonical province names and codes. Aliases are deliberately reviewed and unique.
PROVINCES_V1: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("11", "Aceh", ()),
    ("12", "Sumatera Utara", ("North Sumatra",)),
    ("13", "Sumatera Barat", ("West Sumatra",)),
    ("14", "Riau", ()),
    ("15", "Jambi", ()),
    ("16", "Sumatera Selatan", ("South Sumatra",)),
    ("17", "Bengkulu", ()),
    ("18", "Lampung", ()),
    ("19", "Kepulauan Bangka Belitung", ("Bangka Belitung",)),
    ("21", "Kepulauan Riau", ("Riau Islands",)),
    ("31", "DKI Jakarta", ("Jakarta",)),
    ("32", "Jawa Barat", ("West Java",)),
    ("33", "Jawa Tengah", ("Central Java",)),
    ("34", "DI Yogyakarta", ("Yogyakarta",)),
    ("35", "Jawa Timur", ("East Java",)),
    ("36", "Banten", ()),
    ("51", "Bali", ()),
    ("52", "Nusa Tenggara Barat", ("West Nusa Tenggara",)),
    ("53", "Nusa Tenggara Timur", ("East Nusa Tenggara",)),
    ("61", "Kalimantan Barat", ("West Kalimantan",)),
    ("62", "Kalimantan Tengah", ("Central Kalimantan",)),
    ("63", "Kalimantan Selatan", ("South Kalimantan",)),
    ("64", "Kalimantan Timur", ("East Kalimantan",)),
    ("65", "Kalimantan Utara", ("North Kalimantan",)),
    ("71", "Sulawesi Utara", ("North Sulawesi",)),
    ("72", "Sulawesi Tengah", ("Central Sulawesi",)),
    ("73", "Sulawesi Selatan", ("South Sulawesi",)),
    ("74", "Sulawesi Tenggara", ("Southeast Sulawesi",)),
    ("75", "Gorontalo", ()),
    ("76", "Sulawesi Barat", ("West Sulawesi",)),
    ("81", "Maluku", ()),
    ("82", "Maluku Utara", ("North Maluku",)),
    ("91", "Papua Barat", ("West Papua",)),
    ("92", "Papua Barat Daya", ("Southwest Papua",)),
    ("94", "Papua", ()),
    ("95", "Papua Selatan", ("South Papua",)),
    ("96", "Papua Tengah", ("Central Papua",)),
    ("97", "Papua Pegunungan", ("Highland Papua",)),
)

MONTHS = {
    "january": 1,
    "januari": 1,
    "february": 2,
    "februari": 2,
    "march": 3,
    "maret": 3,
    "april": 4,
    "may": 5,
    "mei": 5,
    "june": 6,
    "juni": 6,
    "july": 7,
    "juli": 7,
    "august": 8,
    "agustus": 8,
    "september": 9,
    "october": 10,
    "oktober": 10,
    "november": 11,
    "december": 12,
    "desember": 12,
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def _alias_index() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for code, official, aliases in PROVINCES_V1:
        for name in (official, *aliases):
            key = _normalize(name)
            if key in result:
                raise RuntimeError(f"duplicate province alias: {key}")
            result[key] = (code, official)
    return result


ALIASES_V1 = _alias_index()
_MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))
SUPPORTED_DATA_YEARS = frozenset({2023, 2024, 2025})


class ChatFilterResolver:
    def resolve(
        self,
        message: str,
        *,
        province_code: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> ResolvedChatContext:
        normalized = _normalize(message)
        raw_hits: list[tuple[int, int, tuple[str, str]]] = []
        for alias, value in ALIASES_V1.items():
            for match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
                raw_hits.append((match.start(), match.end(), value))
        # Prefer a complete canonical name over a shorter province name nested inside it
        # (for example Kepulauan Riau over Riau, or Papua Barat Daya over Papua).
        maximal_hits = [
            hit
            for hit in raw_hits
            if not any(
                other[0] <= hit[0]
                and other[1] >= hit[1]
                and (other[1] - other[0]) > (hit[1] - hit[0])
                for other in raw_hits
            )
        ]
        ordered_hits = sorted(maximal_hits, key=lambda hit: hit[0])
        message_provinces = tuple(dict.fromkeys(hit[2] for hit in ordered_hits))
        message_province = message_provinces[0] if message_provinces else None

        year_mentions = tuple(
            dict.fromkeys(
                int(value)
                for value in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", normalized)
            )
        )
        year_comparison = bool(
            2 <= len(year_mentions) <= 3
            and set(year_mentions) <= SUPPORTED_DATA_YEARS
            and re.search(r"\b(compare|comparison|versus|vs|bandingkan|perbandingan)\b", normalized)
        )
        dates = (
            (
                ResolutionStatus.RESOLVED,
                date(min(year_mentions), 1, 1),
                date(max(year_mentions), 12, 31),
                FilterSource.MESSAGE,
                (),
            )
            if year_comparison
            else self._dates(message, date_from, date_to)
        )
        if dates[0] != ResolutionStatus.RESOLVED:
            return ResolvedChatContext(
                province_code=message_province[0] if message_province else province_code,
                province_codes=tuple(item[0] for item in message_provinces),
                province_source="message"
                if message_province
                else ("ui_context" if province_code else "absent"),
                status=dates[0],
                codes=dates[4],
            )
        resolved_from, resolved_to, date_source = dates[1], dates[2], dates[3]
        final_province = message_province[0] if message_province else province_code
        if not final_province or not resolved_from or not resolved_to:
            missing = []
            if not final_province:
                missing.append("missing_province")
            if not resolved_from or not resolved_to:
                missing.append("missing_date_range")
            return ResolvedChatContext(
                province_code=final_province,
                province_codes=(
                    tuple(item[0] for item in message_provinces)
                    if message_provinces
                    else ((province_code,) if province_code else ())
                ),
                date_from=resolved_from,
                date_to=resolved_to,
                province_source="message"
                if message_province
                else ("ui_context" if province_code else "absent"),
                date_source=date_source,
                status="needs_clarification",
                codes=tuple(missing),
            )
        if (
            resolved_from.year not in SUPPORTED_DATA_YEARS
            or resolved_to.year not in SUPPORTED_DATA_YEARS
        ):
            return ResolvedChatContext(status="invalid", codes=("date_out_of_coverage",))
        return ResolvedChatContext(
            province_code=final_province,
            province_codes=(
                tuple(item[0] for item in message_provinces)
                if message_provinces
                else ((province_code,) if province_code else ())
            ),
            date_from=resolved_from,
            date_to=resolved_to,
            comparison_years=tuple(sorted(year_mentions)) if year_comparison else (),
            province_source="message" if message_province else "ui_context",
            date_source=date_source,
            mention_labels=tuple(
                item
                for item in (
                    *(item[1] for item in message_provinces),
                    "explicit_date" if date_source == FilterSource.MESSAGE else None,
                )
                if item
            ),
            status="resolved",
        )

    def _dates(self, message: str, ui_from: date | None, ui_to: date | None):
        lowered = unicodedata.normalize("NFKC", message).casefold()
        if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", lowered):
            return ResolutionStatus.INVALID, None, None, FilterSource.ABSENT, ("ambiguous_date",)
        if re.search(r"\b(last month|bulan lalu|kemarin|next month|bulan depan)\b", lowered):
            return ResolutionStatus.INVALID, None, None, FilterSource.ABSENT, ("relative_date",)
        if re.search(r"\b(after|before|since|setelah|sebelum|sejak)\b", lowered):
            return ResolutionStatus.INVALID, None, None, FilterSource.ABSENT, ("open_ended_date",)

        iso = re.findall(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", lowered)
        if iso:
            try:
                parsed = [date.fromisoformat(item) for item in iso]
            except ValueError:
                return ResolutionStatus.INVALID, None, None, FilterSource.ABSENT, ("invalid_date",)
            if len(parsed) > 2:
                return (
                    ResolutionStatus.NEEDS_CLARIFICATION,
                    None,
                    None,
                    FilterSource.ABSENT,
                    ("multiple_dates",),
                )
            start, end = parsed[0], parsed[-1]
            if end < start:
                return (
                    ResolutionStatus.INVALID,
                    None,
                    None,
                    FilterSource.ABSENT,
                    ("reversed_range",),
                )
            return ResolutionStatus.RESOLVED, start, end, FilterSource.MESSAGE, ()

        month_match = re.search(rf"\b({_MONTH_PATTERN})\b(?:\s+(\d{{4}}))?", lowered)
        if month_match:
            year_text = month_match.group(2)
            if year_text:
                year = int(year_text)
            elif ui_from and ui_to and ui_from.year == ui_to.year:
                year = ui_from.year
            else:
                return (
                    ResolutionStatus.NEEDS_CLARIFICATION,
                    None,
                    None,
                    FilterSource.ABSENT,
                    ("missing_year",),
                )
            month = MONTHS[month_match.group(1)]
            return (
                ResolutionStatus.RESOLVED,
                date(year, month, 1),
                date(year, month, calendar.monthrange(year, month)[1]),
                FilterSource.MESSAGE,
                (),
            )

        years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", lowered)
        if years:
            if len(set(years)) != 1:
                return (
                    ResolutionStatus.NEEDS_CLARIFICATION,
                    None,
                    None,
                    FilterSource.ABSENT,
                    ("multiple_years",),
                )
            year = int(years[0])
            return (
                ResolutionStatus.RESOLVED,
                date(year, 1, 1),
                date(year, 12, 31),
                FilterSource.MESSAGE,
                (),
            )
        return (
            ResolutionStatus.RESOLVED,
            ui_from,
            ui_to,
            (FilterSource.UI_CONTEXT if ui_from or ui_to else FilterSource.ABSENT),
            (),
        )
