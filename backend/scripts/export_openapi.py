#!/usr/bin/env python3
"""Export the canonical A01 OpenAPI snapshot deterministically."""

from __future__ import annotations

import json
from pathlib import Path

from wildfire_api.main import create_app


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    destination = project_root / "docs/openapi/api_v1.2.0.openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    destination.write_text(rendered, encoding="utf-8")
    print(f"wrote {destination.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
