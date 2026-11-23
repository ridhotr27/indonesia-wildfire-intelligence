import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from data.scripts.firms_historical_access import (
    ConfigurationError,
    DownloadError,
    MAP_KEY_ENV,
    build_area_url,
    download_csv,
    get_map_key,
)

EXPECTED_TEST_CSV = (
    b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    b"satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    b"0,100,300,0.4,0.4,2023-09-01,0001,N,VIIRS,n,2,280,1,D\n"
)


class FirmsHistoricalAccessTest(unittest.TestCase):
    def test_map_key_is_required_from_environment_mapping(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, MAP_KEY_ENV):
            get_map_key({})

    def test_area_request_is_bounded_and_contains_supplied_key(self) -> None:
        url = build_area_url(
            source="VIIRS_SNPP_SP",
            bbox="95,-11,141,6",
            days=5,
            start_date="2023-09-01",
            map_key="secret-key",
        )
        self.assertIn("/secret-key/VIIRS_SNPP_SP/95,-11,141,6/5/2023-09-01", url)
        with self.assertRaises(ConfigurationError):
            build_area_url(
                source="VIIRS_SNPP_SP",
                bbox="95,-11,141,6",
                days=6,
                start_date="2023-09-01",
                map_key="secret-key",
            )

    def test_download_evidence_never_contains_request_url_or_secret(self) -> None:
        csv_bytes = EXPECTED_TEST_CSV

        def opener(_request, *, timeout):
            self.assertGreater(timeout, 0)
            return io.BytesIO(csv_bytes)

        with tempfile.TemporaryDirectory() as directory:
            evidence = download_csv(
                url="https://example.test/api/secret-key/data",
                destination=Path(directory) / "sample.csv",
                access_method="authenticated-area-api",
                product="VIIRS_SNPP_SP",
                date_from="2023-09-01",
                day_count=1,
                credential_env=MAP_KEY_ENV,
                opener=opener,
            )
            rendered = repr(evidence)
            self.assertNotIn("secret-key", rendered)
            self.assertNotIn("example.test", rendered)
            self.assertEqual(evidence.credential_env, MAP_KEY_ENV)

    def test_network_error_does_not_echo_secret_url(self) -> None:
        def opener(_request, *, timeout):
            raise URLError("network failed for secret-key")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DownloadError) as raised:
                download_csv(
                    url="https://example.test/api/secret-key/data",
                    destination=Path(directory) / "sample.csv",
                    access_method="authenticated-area-api",
                    product="VIIRS_SNPP_SP",
                    date_from="2023-09-01",
                    day_count=1,
                    credential_env=MAP_KEY_ENV,
                    opener=opener,
                    sleeper=lambda _seconds: None,
                )
            self.assertNotIn("secret-key", str(raised.exception))

    def test_transient_failure_retries_then_publishes_atomically(self) -> None:
        csv_bytes = EXPECTED_TEST_CSV
        attempts = 0
        delays = []

        def opener(_request, *, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise URLError("transient secret-key failure")
            return io.BytesIO(csv_bytes)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.csv"
            evidence = download_csv(
                url="https://example.test/api/secret-key/data",
                destination=destination,
                access_method="authenticated-area-api",
                product="VIIRS_SNPP_SP",
                date_from="2023-09-01",
                day_count=1,
                credential_env=MAP_KEY_ENV,
                opener=opener,
                retry_delay_seconds=0.25,
                sleeper=delays.append,
            )
            self.assertEqual(attempts, 2)
            self.assertEqual(delays, [0.25])
            self.assertEqual(destination.read_bytes(), csv_bytes)
            self.assertEqual(evidence.bytes, len(csv_bytes))
            self.assertEqual([path for path in destination.parent.iterdir()], [destination])

    def test_retry_exhaustion_preserves_destination_and_cleans_temporary_files(self) -> None:
        attempts = 0

        def opener(_request, *, timeout):
            nonlocal attempts
            attempts += 1
            raise URLError("failed for secret-key")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.csv"
            destination.write_bytes(b"previous-good-artifact")
            with self.assertRaises(DownloadError) as raised:
                download_csv(
                    url="https://example.test/api/secret-key/data",
                    destination=destination,
                    access_method="authenticated-area-api",
                    product="VIIRS_SNPP_SP",
                    date_from="2023-09-01",
                    day_count=1,
                    credential_env=MAP_KEY_ENV,
                    opener=opener,
                    max_attempts=3,
                    sleeper=lambda _seconds: None,
                )
            self.assertEqual(attempts, 3)
            self.assertNotIn("secret-key", str(raised.exception))
            self.assertEqual(destination.read_bytes(), b"previous-good-artifact")
            self.assertEqual([path for path in destination.parent.iterdir()], [destination])

    def test_local_filesystem_error_is_not_retried_or_allowed_to_overwrite(self) -> None:
        attempts = 0

        def opener(_request, *, timeout):
            nonlocal attempts
            attempts += 1
            return io.BytesIO(EXPECTED_TEST_CSV)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.csv"
            destination.write_bytes(b"previous-good-artifact")
            with patch(
                "data.scripts.firms_historical_access.tempfile.NamedTemporaryFile",
                side_effect=OSError("local disk failure"),
            ):
                with self.assertRaisesRegex(OSError, "local disk failure"):
                    download_csv(
                        url="https://example.test/api/secret-key/data",
                        destination=destination,
                        access_method="authenticated-area-api",
                        product="VIIRS_SNPP_SP", date_from="2023-09-01",
                        day_count=1, credential_env=MAP_KEY_ENV, opener=opener,
                        sleeper=lambda _seconds: self.fail("must not retry"),
                    )
            self.assertEqual(attempts, 1)
            self.assertEqual(destination.read_bytes(), b"previous-good-artifact")
            self.assertEqual([path for path in destination.parent.iterdir()], [destination])

    def test_non_retryable_http_4xx_uses_one_attempt_and_redacts_url(self) -> None:
        attempts = 0

        def opener(request, *, timeout):
            nonlocal attempts
            attempts += 1
            raise HTTPError(request.full_url, 404, "secret-key", None, None)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.csv"
            with self.assertRaises(DownloadError) as raised:
                download_csv(
                    url="https://example.test/api/secret-key/data",
                    destination=destination,
                    access_method="authenticated-area-api",
                    product="VIIRS_SNPP_SP", date_from="2023-09-01",
                    day_count=1, credential_env=MAP_KEY_ENV, opener=opener,
                    sleeper=lambda _seconds: self.fail("must not retry"),
                )
            self.assertEqual(attempts, 1)
            self.assertNotIn("secret-key", str(raised.exception))
            self.assertEqual(list(destination.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
