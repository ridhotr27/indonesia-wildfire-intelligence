"""Opt-in I01 test; requires a seeded ClickHouse and its ephemeral reader credentials."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    not os.getenv("I01_CLICKHOUSE_URL"),
    reason="set I01_CLICKHOUSE_URL and reader credentials for the live I01 check",
)
def test_live_clickhouse_backend_parity_and_permissions() -> None:
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/validate_i01_clickhouse.py"),
            "--url",
            os.environ["I01_CLICKHOUSE_URL"],
            "--database",
            os.getenv("I01_CLICKHOUSE_DATABASE", "wildfire"),
            "--username",
            os.environ["I01_CLICKHOUSE_USERNAME"],
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"api_data_status": "verified"' in result.stdout
    assert '"riau_september_2023": 687' in result.stdout
