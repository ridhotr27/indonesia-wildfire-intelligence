#!/usr/bin/env python3
"""Bounded NASA FIRMS feasibility downloads with optional environment-only auth."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


MAP_KEY_ENV = "NASA_FIRMS_MAP_KEY"
API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
COUNTRY_BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
ALLOWED_API_SOURCES = {
    "VIIRS_SNPP_SP",
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_SP",
    "VIIRS_NOAA21_NRT",
}
ALLOWED_COUNTRY_PRODUCTS = {"viirs-snpp", "viirs-jpss1", "viirs-jpss2"}
EXPECTED_VIIRS_PREFIX = (
    b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    b"satellite,instrument,confidence,version,bright_ti5,frp,daynight"
)


class ConfigurationError(ValueError):
    """Raised for missing credentials or unsafe request parameters."""


class DownloadError(RuntimeError):
    """Raised when a response cannot be safely used as FIRMS CSV data."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class DownloadEvidence:
    destination: str
    bytes: int
    sha256: str
    access_method: str
    product: str
    date_from: str | None
    day_count: int | None
    credential_env: str | None


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigurationError("date must use YYYY-MM-DD") from exc


def validate_bbox(raw: str) -> str:
    parts = raw.split(",")
    if len(parts) != 4:
        raise ConfigurationError("bbox must be west,south,east,north")
    try:
        west, south, east, north = (float(value) for value in parts)
    except ValueError as exc:
        raise ConfigurationError("bbox values must be numeric") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ConfigurationError("bbox coordinates are out of order or range")
    return ",".join(f"{value:g}" for value in (west, south, east, north))


def get_map_key(environ: dict[str, str] | os._Environ[str] = os.environ) -> str:
    key = environ.get(MAP_KEY_ENV, "").strip()
    if not key:
        raise ConfigurationError(
            f"{MAP_KEY_ENV} is required for the FIRMS area API; "
            "set it in the process environment, never in source control"
        )
    if any(character.isspace() for character in key):
        raise ConfigurationError(f"{MAP_KEY_ENV} must not contain whitespace")
    return key


def build_area_url(
    *, source: str, bbox: str, days: int, start_date: str, map_key: str
) -> str:
    if source not in ALLOWED_API_SOURCES:
        raise ConfigurationError(f"unsupported FIRMS source: {source}")
    normalized_bbox = validate_bbox(bbox)
    if not 1 <= days <= 5:
        raise ConfigurationError("FIRMS area API day count must be between 1 and 5")
    parsed_date = parse_iso_date(start_date)
    return "/".join(
        (
            API_BASE,
            quote(map_key, safe=""),
            quote(source, safe=""),
            quote(normalized_bbox, safe=","),
            str(days),
            parsed_date.isoformat(),
        )
    )


def build_country_url(*, product: str, year: int) -> str:
    if product not in ALLOWED_COUNTRY_PRODUCTS:
        raise ConfigurationError(f"unsupported country-summary product: {product}")
    if not 2012 <= year <= date.today().year:
        raise ConfigurationError("country-summary year is outside the VIIRS era")
    return f"{COUNTRY_BASE}/{product}_{year}_Indonesia.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_response(
    request: Request,
    *,
    timeout: float,
    opener: Callable[..., BinaryIO],
) -> BinaryIO:
    try:
        return opener(request, timeout=timeout)
    except HTTPError as exc:
        # Never include the request URL: authenticated API URLs contain the key.
        raise DownloadError(
            f"FIRMS request failed: {type(exc).__name__}",
            retryable=exc.code == 429 or 500 <= exc.code <= 599,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise DownloadError(
            f"FIRMS request failed: {type(exc).__name__}", retryable=True
        ) from exc


def _download_once(
    *, request: Request, destination: Path, timeout: float,
    opener: Callable[..., BinaryIO],
) -> None:
    temporary_path: Path | None = None
    try:
        with _open_response(request, timeout=timeout, opener=opener) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb", delete=False, dir=destination.parent
            ) as temporary:
                temporary_path = Path(temporary.name)
                try:
                    prefix = response.read(len(EXPECTED_VIIRS_PREFIX))
                except (HTTPError, URLError, TimeoutError, OSError) as exc:
                    raise DownloadError(
                        f"FIRMS response read failed: {type(exc).__name__}",
                        retryable=True,
                    ) from exc
                if prefix != EXPECTED_VIIRS_PREFIX:
                    raise DownloadError(
                        "response is not the expected VIIRS CSV; body suppressed"
                    )
                temporary.write(prefix)
                while True:
                    try:
                        chunk = response.read(1024 * 1024)
                    except (HTTPError, URLError, TimeoutError, OSError) as exc:
                        raise DownloadError(
                            f"FIRMS response read failed: {type(exc).__name__}",
                            retryable=True,
                        ) from exc
                    if not chunk:
                        break
                    temporary.write(chunk)
        if temporary_path is None:
            raise DownloadError("download did not create a temporary file")
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def download_csv(
    *,
    url: str,
    destination: Path,
    access_method: str,
    product: str,
    date_from: str | None,
    day_count: int | None,
    credential_env: str | None,
    timeout: float = 180.0,
    opener: Callable[..., BinaryIO] = urlopen,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
    sleeper: Callable[[float], None] = time.sleep,
) -> DownloadEvidence:
    if not 1 <= max_attempts <= 5:
        raise ConfigurationError("download max_attempts must be between 1 and 5")
    if not 0 <= retry_delay_seconds <= 30:
        raise ConfigurationError("download retry delay must be between 0 and 30 seconds")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "indonesia-wildfire-feasibility/1.0"})
    for attempt in range(1, max_attempts + 1):
        try:
            _download_once(
                request=request, destination=destination, timeout=timeout, opener=opener
            )
            break
        except DownloadError as exc:
            if not exc.retryable or attempt == max_attempts:
                raise
            sleeper(retry_delay_seconds * attempt)

    return DownloadEvidence(
        destination=str(destination),
        bytes=destination.stat().st_size,
        sha256=sha256(destination),
        access_method=access_method,
        product=product,
        date_from=date_from,
        day_count=day_count,
        credential_env=credential_env,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    config = subparsers.add_parser("check-config")
    config.set_defaults(command="check-config")

    country = subparsers.add_parser("public-country")
    country.add_argument("--product", choices=sorted(ALLOWED_COUNTRY_PRODUCTS), required=True)
    country.add_argument("--year", type=int, required=True)
    country.add_argument("--output", type=Path, required=True)

    area = subparsers.add_parser("area-api")
    area.add_argument("--source", choices=sorted(ALLOWED_API_SOURCES), required=True)
    area.add_argument("--bbox", required=True)
    area.add_argument("--days", type=int, required=True)
    area.add_argument("--start-date", required=True)
    area.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "check-config":
        print(
            json.dumps(
                {
                    "credential_env": MAP_KEY_ENV,
                    "configured": bool(os.environ.get(MAP_KEY_ENV, "").strip()),
                },
                sort_keys=True,
            )
        )
        return

    if args.command == "public-country":
        url = build_country_url(product=args.product, year=args.year)
        evidence = download_csv(
            url=url,
            destination=args.output,
            access_method="public-country-summary-https",
            product=args.product,
            date_from=f"{args.year}-01-01",
            day_count=None,
            credential_env=None,
        )
    else:
        key = get_map_key()
        url = build_area_url(
            source=args.source,
            bbox=args.bbox,
            days=args.days,
            start_date=args.start_date,
            map_key=key,
        )
        evidence = download_csv(
            url=url,
            destination=args.output,
            access_method="authenticated-area-api",
            product=args.source,
            date_from=args.start_date,
            day_count=args.days,
            credential_env=MAP_KEY_ENV,
        )
    # Evidence intentionally excludes the request URL when it can contain a secret.
    print(json.dumps(asdict(evidence), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
