from datetime import UTC, date, datetime, timedelta

from wildfire_api.repositories.hotspots import (
    CoverageRecord,
    ObservationRecord,
    ProductRecord,
    ProvinceCountRecord,
    ProvinceRecord,
    RepositoryMetadata,
)


class MockHotspotRepository:
    """Synthetic development data. Records are deliberately not NASA observations."""

    _metadata = RepositoryMetadata(
        products=(ProductRecord("MOCK_ONLY", "Synthetic fixture (not NASA data)"),),
        provinces=(
            ProvinceRecord("MOCK-WEST", "Synthetic Western Province"),
            ProvinceRecord("MOCK-CENTRAL", "Synthetic Central Province"),
        ),
        date_min=date(2023, 9, 1),
        date_max=date(2023, 10, 31),
        known_unavailable_dates=(),
        source_attribution="Synthetic backend fixture; not NASA FIRMS observations",
        source_url="https://firms.modaps.eosdis.nasa.gov/",
        dataset_version="mock-v1-a01-contract",
        data_freshness=None,
        data_status="mock",
    )
    _observations = (
        ObservationRecord(
            "mock-observation-001",
            "MOCK_ONLY",
            "MOCK-WEST",
            datetime(2023, 9, 5, 1, 0, tzinfo=UTC),
            0.0,
            100.0,
            "n",
            4.2,
            "D",
        ),
        ObservationRecord(
            "mock-observation-002",
            "MOCK_ONLY",
            "MOCK-WEST",
            datetime(2023, 9, 18, 2, 0, tzinfo=UTC),
            -1.0,
            101.0,
            "h",
            7.8,
            "N",
        ),
        ObservationRecord(
            "mock-observation-003",
            "MOCK_ONLY",
            "MOCK-WEST",
            datetime(2023, 10, 2, 3, 0, tzinfo=UTC),
            -2.0,
            102.0,
            "l",
            0.0,
            "D",
        ),
        ObservationRecord(
            "mock-observation-004",
            "MOCK_ONLY",
            "MOCK-CENTRAL",
            datetime(2023, 10, 10, 4, 0, tzinfo=UTC),
            -3.0,
            113.0,
            "n",
            2.5,
            "N",
        ),
    )

    async def metadata(self) -> RepositoryMetadata:
        return self._metadata

    async def count_by_month(
        self,
        *,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for observation in self._observations:
            acquired_date = observation.acquired_at_utc.date()
            if (
                observation.product_id == product_id
                and observation.province_code in province_codes
                and date_from <= acquired_date <= date_to
            ):
                period = acquired_date.strftime("%Y-%m")
                counts[period] = counts.get(period, 0) + 1
        return counts

    async def count_by_year(
        self, *, product_id: str, province_code: str, years: tuple[int, ...]
    ) -> dict[int, int]:
        return {
            year: sum(
                item.product_id == product_id
                and item.province_code == province_code
                and item.acquired_at_utc.year == year
                for item in self._observations
            )
            for year in years
        }

    async def observations(
        self,
        *,
        product_id: str,
        province_code: str,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> tuple[list[ObservationRecord], bool]:
        matches = [
            observation
            for observation in self._observations
            if observation.product_id == product_id
            and observation.province_code == province_code
            and date_from <= observation.acquired_at_utc.date() <= date_to
        ]
        return matches[:limit], len(matches) > limit

    async def count_by_province(
        self, *, product_id: str, province_codes: tuple[str, ...], date_from: date, date_to: date
    ) -> tuple[tuple[ProvinceCountRecord, ...], int]:
        selected = province_codes or tuple(item.province_code for item in self._metadata.provinces)
        rows = []
        for order, code in enumerate((item.province_code for item in self._metadata.provinces), 1):
            if code not in selected:
                continue
            name = next(
                item.display_name for item in self._metadata.provinces if item.province_code == code
            )
            count = sum(
                item.product_id == product_id
                and item.province_code == code
                and date_from <= item.acquired_at_utc.date() <= date_to
                for item in self._observations
            )
            rows.append(ProvinceCountRecord(code, name, order, count))
        return tuple(rows), 0

    async def coverage(
        self,
        *,
        product_id: str,
        date_from: date,
        date_to: date,
    ) -> tuple[CoverageRecord, ...]:
        current = date_from
        rows: list[CoverageRecord] = []
        while current <= date_to:
            count = sum(
                observation.product_id == product_id
                and observation.acquired_at_utc.date() == current
                for observation in self._observations
            )
            rows.append(
                CoverageRecord(
                    date_utc=current,
                    coverage_status=(
                        "observations_present" if count else "zero_detections_verified"
                    ),
                    observation_count=count,
                    evidence_url=(
                        None if count else "https://example.invalid/synthetic-zero-evidence"
                    ),
                    note="Synthetic fixture coverage; not NASA observations.",
                )
            )
            current += timedelta(days=1)
        return tuple(rows)
