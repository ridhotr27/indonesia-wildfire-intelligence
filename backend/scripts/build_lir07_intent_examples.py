#!/usr/bin/env python3
"""Build reviewed LIR-07 routing examples from the development partition only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evaluation.lir01_models import Lir01Corpus
from wildfire_api.agent.semantic_intent import (
    IntentExample,
    IntentExampleSet,
    load_example_set,
)

SLOTS = {
    "single_province_count": (("province", "date"), (), 1, 1),
    "monthly_trend": (("province", "date"), (), 1, 1),
    "multi_province_summary": (("province", "date"), (), 2, 38),
    "province_ranking": (("date",), ("direction", "top_n"), 0, 38),
    "documentation_semantics": ((), (), 0, 38),
    "combined_analytics_documentation": (("province", "date"), (), 1, 38),
}


def _is_training_family(family_id: str) -> bool:
    """Keep calibration families out of the semantic example index."""
    return hashlib.sha256(family_id.encode()).digest()[0] % 2 == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = Lir01Corpus.model_validate_json(args.corpus.read_bytes())
    base = load_example_set(args.base)
    generated: list[IntentExample] = []
    for case in corpus.cases:
        if (
            case.partition != "development"
            or case.category == "multi_turn"
            or not _is_training_family(case.semantic_family_id)
        ):
            continue
        if case.intent not in SLOTS:
            continue
        required, optional, minimum, maximum = SLOTS[case.intent]
        generated.append(
            IntentExample(
                id=f"lir07.{case.id.removeprefix('lir01.')}",
                text=case.current_message,
                language=case.language,
                intent=case.intent,
                required_slots=required,
                optional_slots=optional,
                min_provinces=minimum,
                max_provinces=maximum,
                review_status="reviewed",
                source_category="known_regression",
            )
        )
    examples = IntentExampleSet(
        dataset_version="lir07-intent-examples-v3.0.0",
        taxonomy_version=base.taxonomy_version,
        examples=(*base.examples, *generated),
    )
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable examples: {args.output}")
    args.output.write_text(
        json.dumps(examples.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(examples.examples)} reviewed development examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
