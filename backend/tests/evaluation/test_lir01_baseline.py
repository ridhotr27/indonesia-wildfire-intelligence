import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPOSITORY = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from evaluation.build_lir01_corpus import PROVINCES, build  # noqa: E402
from evaluation.lir01_models import Lir01Corpus  # noqa: E402
from evaluation.run_lir01_baseline import evaluate, predict, run  # noqa: E402

CORPUS_PATH = BACKEND / "evaluation" / "lir01_intent_routing_corpus_v1.json"
MANIFEST_PATH = BACKEND / "evaluation" / "lir01_intent_routing_corpus_v1.manifest.json"
BASELINE_PATHS = tuple(
    BACKEND / "evaluation" / f"lir01_variant_{variant}_baseline_v1.json" for variant in ("a", "b")
)


def corpus() -> Lir01Corpus:
    return Lir01Corpus.model_validate_json(CORPUS_PATH.read_bytes())


def normalized_signature(case: object) -> str:
    return "|".join(
        [
            " ".join(case.current_message.casefold().split()),
            *(" ".join(turn.content.casefold().split()) for turn in case.history),
        ]
    )


def character_trigrams(text: str) -> set[str]:
    normalized = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
    return {normalized[index : index + 3] for index in range(max(1, len(normalized) - 2))}


def test_corpus_schema_manifest_hash_and_reproducibility() -> None:
    frozen = corpus()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert build().model_dump(mode="json") == frozen.model_dump(mode="json")
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["dataset_version"] == frozen.dataset_version
    assert manifest["created_at"] == "2026-11-15"
    assert manifest["case_count"] == len(frozen.cases)
    assert manifest["corpus_sha256"] == hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()
    assert manifest["prohibited_content_scan"] == {
        "status": "passed",
        "production_chat_cases": 0,
        "numeric_result_claims": 0,
    }
    assert manifest["final_holdout_status"].startswith("sealed")


def test_corpus_meets_composition_language_and_holdout_intent_minima() -> None:
    cases = corpus().cases
    category_counts = Counter(case.category for case in cases)
    assert len(cases) == 1_200
    assert category_counts >= Counter(
        {
            "analytics": 240,
            "nasa_rag": 120,
            "combined": 100,
            "multi_turn": 120,
            "ambiguous_clarification": 100,
            "unsupported_adversarial": 120,
        }
    )
    language_counts = Counter(case.language for case in cases)
    assert language_counts["en"] / len(cases) >= 0.35
    assert language_counts["id"] / len(cases) >= 0.35
    assert language_counts["mixed"] / len(cases) >= 0.15
    holdout = [case for case in cases if case.partition == "final_holdout"]
    supported = Counter(
        case.intent for case in holdout if case.expected_route in {"analytics", "rag", "combined"}
    )
    assert supported
    assert min(supported.values()) >= 40


def test_all_cases_have_complete_labels_and_existing_truth_sources() -> None:
    cases = corpus().cases
    for case in cases:
        assert case.expected_reason_code
        assert case.expected_calls.forbidden_tool_calls == 0
        assert set(case.expected_calls.planner_calls) == {"A", "B", "C", "D"}
        assert case.expected_entities.provenance
        assert case.truth_reference.numeric_result_claimed is False
        assert all((REPOSITORY / path).is_file() for path in case.truth_reference.source_paths)
        if case.expected_route in {"analytics", "combined"}:
            assert case.expected_entities.product_id == "VNP14IMG.002_SNPP_FIRMS_SP"
            assert case.expected_entities.metric_id == "satellite_hotspot_detections"
    assert all("sumbar" not in case.current_message.casefold() for case in cases)


def test_family_splits_exact_duplicates_and_near_duplicate_leakage() -> None:
    cases = corpus().cases
    signatures = [normalized_signature(case) for case in cases]
    assert len(signatures) == len(set(signatures))
    family_partitions: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        family_partitions[case.semantic_family_id].add(case.partition)
    assert all(len(partitions) == 1 for partitions in family_partitions.values())

    grams = [character_trigrams(case.current_message) for case in cases]
    maximum_cross_partition_similarity = 0.0
    for left_index, left in enumerate(cases):
        for right_index in range(left_index + 1, len(cases)):
            right = cases[right_index]
            if left.partition == right.partition or left.category != right.category:
                continue
            union = grams[left_index] | grams[right_index]
            similarity = len(grams[left_index] & grams[right_index]) / len(union)
            maximum_cross_partition_similarity = max(maximum_cross_partition_similarity, similarity)
    assert maximum_cross_partition_similarity < 0.80


def test_data_contract_window_and_gap_truth_are_frozen() -> None:
    frozen = corpus()
    assert tuple(item.isoformat() for item in frozen.supported_window) == (
        "2023-01-01",
        "2023-12-31",
    )
    assert tuple(item.isoformat() for item in frozen.known_unavailable_dates) == (
        "2023-07-26",
        "2023-07-27",
    )
    assert frozen.product_id == "VNP14IMG.002_SNPP_FIRMS_SP"


def test_data_owned_geography_and_edge_labels_match_approved_sources() -> None:
    crosswalk_payload = json.loads(
        (REPOSITORY / "data/provenance/d03b_reusable_boundary.json").read_text(encoding="utf-8")
    )
    crosswalk = {
        row["canonical_code"]: row["canonical_name"] for row in crosswalk_payload["crosswalk"]
    }
    assert len(crosswalk) == 38
    assert {(code, name_id) for code, _name_en, name_id in PROVINCES} <= set(crosswalk.items())
    assert crosswalk["91"] == "Papua"
    assert crosswalk["92"] == "Papua Barat"

    cases = corpus().cases
    known_codes = set(crosswalk)
    assert all(set(case.expected_entities.province_codes) <= known_codes for case in cases)
    data_reviewed = [
        case
        for case in cases
        if case.expected_route in {"analytics", "combined", "clarification", "unsupported"}
    ]
    assert all("data_engineer" in case.reviewer_roles for case in data_reviewed)
    province_cases = [case for case in cases if case.expected_entities.province_codes]
    assert all(
        "data/provenance/d03b_reusable_boundary.json" in case.truth_reference.source_paths
        for case in province_cases
    )

    tags = {tag for case in cases for tag in case.safety_tags}
    assert {
        "partial_coverage",
        "wholly_unavailable",
        "unavailable_not_zero",
        "verified_zero_only",
        "zero_ties",
        "dense_rank_ties",
        "null_geography_reported",
        "no_nearest_province_coercion",
    } <= tags
    edge_cases = [
        case
        for case in cases
        if case.semantic_family_id
        in {
            "analytics.095",
            "analytics.096",
            "analytics.097",
            "analytics.098",
            "analytics.099",
        }
    ]
    assert len(edge_cases) == 20
    assert all(case.truth_reference.kind == "contract_fixture" for case in edge_cases)
    assert all(case.truth_reference.numeric_result_claimed is False for case in edge_cases)
    gap_cases = [
        case for case in edge_cases if case.semantic_family_id in {"analytics.095", "analytics.096"}
    ]
    assert all(
        (
            case.expected_entities.direction,
            case.expected_entities.top_n,
            case.expected_entities.ranking_selection,
            case.expected_entities.tie_policy,
            case.expected_entities.geography_scope,
        )
        == (None, None, None, None, None)
        for case in gap_cases
    )
    assert all(
        case.truth_reference.reference_query_ids[:2] == ("MONTHLY_COUNTS", "COVERAGE")
        for case in gap_cases
    )


def test_variant_a_is_repeatable_and_never_executes_forbidden_tools() -> None:
    cases = [case for case in corpus().cases if case.partition == "development"]
    first = evaluate(cases, "A", None)
    second = evaluate(cases, "A", None)
    comparable_fields = (
        "actual_route",
        "actual_operation_ids",
        "route_correct",
        "entity_exact",
        "actual_reason",
        "route_source",
    )
    assert [tuple(row[field] for field in comparable_fields) for row in first["cases"]] == [
        tuple(row[field] for field in comparable_fields) for row in second["cases"]
    ]
    assert first["metrics"]["forbidden_tool_calls"] == 0


class FakeSemanticIndex:
    def __init__(self, *, accepted: bool, intent: str | None, reason: str) -> None:
        self.result = SimpleNamespace(accepted=accepted, intent=intent, reason=reason)

    def match(self, _question: str) -> SimpleNamespace:
        return self.result


def test_variant_b_interface_handles_accepted_and_rejected_matches() -> None:
    target = next(
        case
        for case in corpus().cases
        if case.intent == "province_ranking" and case.partition == "development"
    )
    accepted = predict(
        target,
        variant="B",
        semantic_index=FakeSemanticIndex(
            accepted=True, intent="province_ranking", reason="accepted"
        ),
    )
    rejected = predict(
        target,
        variant="B",
        semantic_index=FakeSemanticIndex(accepted=False, intent=None, reason="below_threshold"),
    )
    assert accepted.route in {"analytics", "clarification"}
    assert accepted.route_source in {"deterministic", "semantic_accepted"}
    assert rejected.route_source in {"deterministic", "semantic_rejected"}


def test_final_holdout_is_sealed_by_default(tmp_path: Path) -> None:
    arguments = argparse.Namespace(
        corpus=CORPUS_PATH,
        variants=("A",),
        partitions=("final_holdout",),
        allow_final_holdout=False,
        output_dir=tmp_path,
        semantic_index=BACKEND / "data" / "semantic-intents",
        semantic_collection="analytics_intent_examples_v1",
        embedding_model="all-minilm",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_timeout_seconds=1.0,
    )
    with pytest.raises(ValueError, match="final_holdout is sealed"):
        asyncio.run(run(arguments))


def test_baseline_result_files_are_immutable(tmp_path: Path) -> None:
    arguments = argparse.Namespace(
        corpus=CORPUS_PATH,
        variants=("A",),
        partitions=("development",),
        allow_final_holdout=False,
        output_dir=tmp_path,
        semantic_index=BACKEND / "data" / "semantic-intents",
        semantic_collection="analytics_intent_examples_v1",
        embedding_model="all-minilm",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_timeout_seconds=1.0,
    )
    outputs = asyncio.run(run(arguments))
    assert len(outputs) == 1
    with pytest.raises(FileExistsError, match="refusing to overwrite immutable result"):
        asyncio.run(run(arguments))


def test_frozen_baseline_artifacts_match_the_unconsumed_corpus() -> None:
    corpus_hash = hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()
    for path in BASELINE_PATHS:
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["schema_version"] == "1.0.0"
        assert result["corpus_sha256"] == corpus_hash
        assert result["partitions"] == ["development", "shadow_validation"]
        assert result["final_holdout_consumed"] is False
        assert result["case_count"] == 800
        assert result["metrics"]["forbidden_tool_calls"] == 0
