from __future__ import annotations

import hashlib
import json
from pathlib import Path

from data.scripts.ingest_firms_v1 import PROVINCES


def write_synthetic_boundary(path: Path) -> str:
    """Write a minimal deterministic 38-province boundary for unit tests."""
    features = []
    for index, (source_code, (canonical_code, canonical_name)) in enumerate(
        sorted(PROVINCES.items())
    ):
        west = 95.0 + (index % 10) * 3.0
        south = -10.0 + (index // 10) * 4.0
        if canonical_code == "14":
            west, south = 100.0, -1.0
        elif canonical_code == "62":
            west, south = 112.0, -3.0
        ring = [
            [west, south],
            [west + 2.0, south],
            [west + 2.0, south + 2.0],
            [west, south + 2.0],
            [west, south],
        ]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "KDPPUM": canonical_code,
                    "WADMPR": canonical_name,
                    "source_code": source_code,
                },
                "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]},
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()
