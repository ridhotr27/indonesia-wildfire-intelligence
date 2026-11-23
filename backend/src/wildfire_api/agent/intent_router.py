from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wildfire_api.agent.filter_resolver import PROVINCES_V1, SUPPORTED_DATA_YEARS
from wildfire_api.agent.state import AgentMode

IntentCode = Literal[
    "analytics_operation",
    "documentation_semantics",
    "combined_explicit",
    "unsupported_causal",
    "unsupported_measure",
    "unsupported_product",
    "unsupported_region",
    "unsupported_date",
    "unsafe_instruction",
    "unrecognized",
]


class IntentDecision(BaseModel):
    """Bounded routing evidence; never contains message text or hidden reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: AgentMode
    reason: str = Field(min_length=1, max_length=240)
    intent_codes: tuple[IntentCode, ...] = Field(min_length=1, max_length=3)
    filters_applicable: bool

    @model_validator(mode="after")
    def filters_match_mode(self) -> IntentDecision:
        if self.filters_applicable != (self.mode in {"analytics", "combined"}):
            raise ValueError("filters_applicable must match an analytics-capable mode")
        return self


class DeterministicIntentRouter:
    """Classify requested operations without treating subject nouns as tool intent."""

    _quoted_span = re.compile(r'"[^"\n]*"|“[^”\n]*”')

    _unsafe_instruction = re.compile(
        r"\b(ignore|override|reveal|leak|dump|bypass)\b.{0,45}"
        r"\b(instructions?|prompts?|secrets?|credentials?|sql|schema)\b|"
        r"\b(?:abaikan|lewati)\b.{0,45}\b(?:kontrol|instruksi|prompt|rahasia|sql|skema)\b|"
        r"\b(execute|run|write|drop|alter|insert|delete)\b.{0,30}\bsql\b",
        re.IGNORECASE,
    )
    _unsupported_measure = re.compile(
        r"\b(burn(?:ed|t)?\s+(?:area|hectares?)|hectares?\s+(?:burned|burnt)|"
        r"hektare\s+terbakar|"
        r"confirmed\s+(?:fires?|wildfires?)|confirmed\s+fire\s+incidents?|"
        r"kebakaran\s+terkonfirmasi|"
        r"wildfire\s+(?:size|area)|fire\s+perimeters?)\b",
        re.IGNORECASE,
    )
    _prediction = re.compile(
        r"\b(predict(?:ion|ed|ive)?|forecast(?:ed|ing)?|prediksi|"
        r"next\s+(?:month|year|week)|bulan\s+depan)\b",
        re.IGNORECASE,
    )
    _unsupported_product = re.compile(r"\b(MODIS|Landsat|Sentinel)\b", re.IGNORECASE)
    _unsupported_region = re.compile(
        r"\b(Malaysia|Singapore|Thailand|Australia|Philippines|Vietnam|Brazil|"
        r"United States|Canada|India|China|Japan|Germany|France)\b",
        re.IGNORECASE,
    )

    # These patterns identify an operation request, not the data nouns it operates on.
    _analytics_operation = re.compile(
        r"\bhow\s+many\b|"
        r"\bhow\s+large\s+was\s+the\s+(?:hotspot\s+)?(?:detection\s+)?count\b|"
        r"\bcount(?:\s+(?:the|of|hotspots?|detections?))\b|"
        r"\bcompare\b|"
        r"\bdetection\s+total\s+belongs\s+to\b|"
        r"\b(?:give|report)\b.{0,55}\b(?:hotspot\s+tally|detection\s+count|jumlah\s+deteksi)\b|"
        r"\bbreak\b.{0,60}\b(?:by\s+month|monthly)\b|"
        r"\bhow\s+did\b.{0,65}\b(?:change|vary)\b.{0,35}\b(?:months?|monthly)\b|"
        r"\b(?:show|display|plot|map|report|provide|return|give|tampilkan)\b.{0,45}"
        r"\b(?:monthly|bulanan|hotspots?|detections?|deteksi|counts?|total|trend|tren|comparison|locations?)\b|"
        r"\bwhat\s+(?:was|is|were|are)\s+the\s+(?:hotspot\s+|detection\s+)?"
        r"(?:count|total|trend)\b|"
        r"\bmonthly\s+(?:hotspot\s+|detection\s+)?(?:count|total|trend|breakdown)\b"
        r"|\bwhich\s+province\b.{0,45}\b(?:most|highest|least|lowest)\b"
        r"|\b(?:name|list)\b.{0,45}\bprovince(?:s)?\b.{0,45}\b(?:lowest|highest|top|bottom|most|least|count)\b"
        r"|\b(?:top|bottom)\s+(?:\d+|one|two|three|four|five)\b.{0,45}\b(?:province|hotspot|detection)"
        r"|\b(?:berapa\s+(?:jumlah|banyak|total)|hitung)\b.{0,60}\b(?:hotspot|deteksi)\b"
        r"|\bbandingkan\b"
        r"|\b(?:berikan|laporkan)\b.{0,55}\b(?:jumlah\s+hotspot|jumlah\s+deteksi|total\s+hotspot)\b"
        r"|\buraikan\b.{0,55}\bmenurut\s+bulan\b"
        r"|\b(?:sebutkan|daftarkan)\b.{0,55}\b(?:provinsi|province)\b.{0,55}\b(?:terendah|tertinggi|teratas|terbanyak|tersedikit|lowest|highest|jumlah|total)\b"
        r"|\btell\s+me\s+about\b.{0,40}\bhotspots?\b"
        r"|\bwhich\s+(?:province\s+)?had\s+(?:more|fewer)\b"
        r"|\bwhich\s+had\s+lebih\s+(?:banyak|sedikit)\b"
        r"|\b(?:separate\s+and\s+combined|terpisah\s+dan\s+gabungan)\b.{0,25}\b(?:counts?|jumlah)\b"
        r"|\bjumlah\s+terpisah\s+dan\s+gabungan\b"
        r"|\bmana\s+yang\s+memiliki\s+lebih\s+(?:banyak|sedikit)\b",
        re.IGNORECASE,
    )

    _documentation_request = re.compile(
        r"\bwhat\s+(?:does|do|is|are)\b|"
        r"\bwhat\b.{0,55}\bdoes\b|"
        r"\bhow\s+should\b|"
        r"\b(?:explain|define|describe)\b|"
        r"\b(?:meaning|definition|interpretation|methodology)\b|"
        r"\bwhat\b.{0,55}\blimitations?\b|\blimitations?\s+apply\b|"
        r"\bwhat\s+is\s+the\s+difference\b|"
        r"\bdifference\s+between\b"
        r"|\bapa\s+(?:itu|arti|artinya)\b|\bjelaskan\b|\bmetodologi\b"
        r"|\b(?:arti|makna)\s+(?:confidence|frp|fire\s+radiative\s+power)\b"
        r"|\bcan\s+hotspots?\s+confirm\b|\bdo\s+hotspots?\s+(?:mean|confirm)\b",
        re.IGNORECASE,
    )
    _semantic_documentation = re.compile(
        r"\b(?:interpret(?:ed|ation)?|measure(?:ment)?\s+of|"
        r"represent(?:s|ed|ation)?|difference\s+between)\b|"
        r"\bwhy\s+(?:(?:can|could|should|does|do|is|are)\s+not|"
        r"can['’]?t|couldn['’]?t|shouldn['’]?t|doesn['’]?t|isn['’]?t|aren['’]?t)\b|"
        r"\bexplain\s+why\b.{0,100}\b(?:not|cannot|can['’]?t|should\s+not)\b|"
        r"\bwhy\b.{0,100}\bnot\s+the\s+same\b|"
        r"\bmengapa\b.{0,100}\b(?:tidak\s+sama|bukan)\b.{0,60}"
        r"\b(?:confirmed|terkonfirmasi)\b",
        re.IGNORECASE,
    )
    _analytics_what_frame = re.compile(
        r"^what\s+(?:was|is|were|are)\s+the\s+(?:hotspot\s+|detection\s+)?"
        r"(?:count|total|trend)\b",
        re.IGNORECASE,
    )
    _causal_activity = re.compile(
        r"\bwhy\s+(?:did|were|was|are|have|has|had|do|does)\b.{0,100}"
        r"\b(?:increas(?:e|ed)|decreas(?:e|ed)|higher|lower|more|fewer|occur(?:red)?)\b|"
        r"\bwhat\s+(?:caused|led\s+to)\b|"
        r"\bexplain\s+(?:why|what\s+led\s+to)\b.{0,100}"
        r"\b(?:increas(?:e|ed)|decreas(?:e|ed)|trend|hotspots?|fires?)\b|"
        r"\b(?:causal\s+explanation|reasons?\s+for|drivers?\s+of)\b|"
        r"\battribut(?:e|ed|ing)\b.{0,60}\bto\b",
        re.IGNORECASE,
    )

    _location_cue = re.compile(r"\b(?:in|within|across)\s+([^?.,;]{1,80})", re.IGNORECASE)
    _approved_locations = frozenset(
        {
            "indonesia",
            "aceh",
            "sumatera utara",
            "sumatera barat",
            "riau",
            "jambi",
            "sumatera selatan",
            "bengkulu",
            "lampung",
            "kepulauan bangka belitung",
            "kepulauan riau",
            "dki jakarta",
            "jawa barat",
            "jawa tengah",
            "di yogyakarta",
            "jawa timur",
            "banten",
            "bali",
            "nusa tenggara barat",
            "nusa tenggara timur",
            "kalimantan barat",
            "kalimantan tengah",
            "kalimantan selatan",
            "kalimantan timur",
            "kalimantan utara",
            "sulawesi utara",
            "sulawesi tengah",
            "sulawesi selatan",
            "sulawesi tenggara",
            "gorontalo",
            "sulawesi barat",
            "maluku",
            "maluku utara",
            "papua barat",
            "papua barat daya",
            "papua",
            "papua selatan",
            "papua tengah",
            "papua pegunungan",
            "north sumatra",
            "west sumatra",
            "south sumatra",
            "west java",
            "central java",
            "east java",
            "west kalimantan",
            "central kalimantan",
            "south kalimantan",
            "east kalimantan",
            "north kalimantan",
        }
    ) | frozenset(
        name.casefold()
        for _, official, aliases in PROVINCES_V1
        for name in (official, *aliases)
    )
    _temporal_location_words = re.compile(
        r"^(?:january|february|march|april|may|june|july|august|september|october|"
        r"november|december|20\d{2}|the\s+(?:selected|current)\s+(?:date\s+range|period)|"
        r"the\s+months?|"
        r"this\s+(?:month|year))\b",
        re.IGNORECASE,
    )
    _context_location_words = re.compile(
        r"^(?:the\s+)?(?:selected|current|this)\s+province\b", re.IGNORECASE
    )
    _explicit_clause_separator = re.compile(
        r"\s*;\s*|\s+and\s+(?=(?:what|how|explain|define|describe|show|display|plot|"
        r"map|report|provide|return|give|count|compare)\b)",
        re.IGNORECASE,
    )

    @staticmethod
    def _normalize(message: str) -> str:
        normalized = unicodedata.normalize("NFKC", message).replace("’", "'")
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _has_unsupported_location_phrase(cls, message: str) -> bool:
        for match in cls._location_cue.finditer(message):
            phrase = match.group(1).strip().casefold()
            if cls._temporal_location_words.search(phrase) or cls._context_location_words.search(
                phrase
            ):
                continue
            if any(
                re.search(rf"\b{re.escape(location)}\b", phrase)
                for location in cls._approved_locations
            ):
                continue
            return True
        return False

    @staticmethod
    def _decision(
        mode: AgentMode,
        reason: str,
        *codes: IntentCode,
    ) -> IntentDecision:
        return IntentDecision(
            mode=mode,
            reason=reason,
            intent_codes=tuple(dict.fromkeys(codes)),
            filters_applicable=mode in {"analytics", "combined"},
        )

    def documentation_query(self, message: str) -> str:
        """Return explicit documentation clauses without analytics instructions.

        The original message remains the source of truth for routing and filter
        resolution. This projection is used only as the retrieval/generation query
        after a combined route has already been selected.
        """

        normalized = self._normalize(message)
        clauses = [
            clause.strip(" ,")
            for clause in self._explicit_clause_separator.split(normalized)
            if clause.strip(" ,")
        ]
        documentation_clauses: list[str] = []
        for clause in clauses:
            decision = self.decide(clause)
            if decision.mode == "rag":
                documentation_clauses.append(clause)
        return "; ".join(documentation_clauses) or normalized

    def decide(self, message: str) -> IntentDecision:
        normalized = self._normalize(message)
        # An operation named inside a quotation is a subject of discussion, not a
        # request to execute that operation. Safety checks still inspect the full
        # message below so quoting cannot bypass an unsafe-instruction denial.
        operation_text = self._quoted_span.sub(" ", normalized)
        analytics = bool(self._analytics_operation.search(operation_text))
        documentation = bool(self._documentation_request.search(normalized))
        semantic_documentation = bool(self._semantic_documentation.search(normalized))
        documentation = documentation or semantic_documentation
        if (
            analytics
            and self._analytics_what_frame.search(normalized)
            and not semantic_documentation
        ):
            documentation = False

        if self._unsafe_instruction.search(normalized):
            return self._decision(
                "unsupported", "Request is outside approved v1 scope.", "unsafe_instruction"
            )

        causal_activity = bool(self._causal_activity.search(normalized))
        if causal_activity and not semantic_documentation:
            return self._decision(
                "unsupported",
                "Causal explanations are not supported by hotspot detections.",
                "unsupported_causal",
            )

        prohibited_measure = bool(self._unsupported_measure.search(normalized))
        if (
            prohibited_measure or self._prediction.search(normalized)
        ) and not semantic_documentation:
            return self._decision(
                "unsupported", "Request is outside approved v1 scope.", "unsupported_measure"
            )

        years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", normalized)}
        unsupported_product = bool(self._unsupported_product.search(normalized))
        unsupported_region = bool(self._unsupported_region.search(normalized))
        unsupported_date = any(year not in SUPPORTED_DATA_YEARS for year in years)
        if analytics and (unsupported_product or unsupported_region or unsupported_date):
            code: IntentCode = (
                "unsupported_product"
                if unsupported_product
                else "unsupported_region"
                if unsupported_region
                else "unsupported_date"
            )
            return self._decision("unsupported", "Request is outside approved v1 scope.", code)
        if not documentation and (unsupported_product or unsupported_region or unsupported_date):
            code = (
                "unsupported_product"
                if unsupported_product
                else "unsupported_region"
                if unsupported_region
                else "unsupported_date"
            )
            return self._decision("unsupported", "Request is outside approved v1 scope.", code)

        if analytics and self._has_unsupported_location_phrase(normalized):
            return self._decision(
                "unsupported",
                "Analytics prose location is unsupported or ambiguous.",
                "unsupported_region",
            )

        if analytics and documentation:
            return self._decision(
                "combined",
                "An explicit analytics operation and NASA documentation are required.",
                "analytics_operation",
                "documentation_semantics",
                "combined_explicit",
            )
        if analytics:
            return self._decision(
                "analytics",
                "A bounded hotspot aggregate is required.",
                "analytics_operation",
            )
        if documentation:
            return self._decision(
                "rag",
                "Official NASA documentation is required.",
                "documentation_semantics",
            )
        return self._decision(
            "unsupported", "No approved tool intent was identified.", "unrecognized"
        )
