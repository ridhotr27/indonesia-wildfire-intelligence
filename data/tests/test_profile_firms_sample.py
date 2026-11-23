from pathlib import Path
import unittest

from data.scripts.profile_firms_sample import profile


SAMPLE = Path("data/raw/nasa_firms/sample_viirs_snpp_2023-07-12.csv")


class FirmsSampleProfileTest(unittest.TestCase):
    def test_pinned_sample_profile_matches_recorded_evidence(self) -> None:
        result = profile(SAMPLE)

        self.assertEqual(result["file"]["bytes"], 6_077_404)
        self.assertEqual(
            result["file"]["sha256"],
            "edf79f62b35ba4485d7c85e01be5f6f61d30ab7b4addcf2eea00e2581982c30f",
        )
        self.assertEqual(result["shape"], {"rows": 74_605, "columns": 14})
        self.assertEqual(result["categorical_counts"]["satellite"], {"N": 74_605})
        self.assertEqual(result["categorical_counts"]["instrument"], {"VIIRS": 74_605})
        self.assertEqual(
            result["categorical_counts"]["version"],
            {"2.0NRT": 69_507, "2.0URT": 5_098},
        )
        self.assertEqual(result["quality"]["invalid_timestamp_count"], 0)
        self.assertEqual(result["quality"]["invalid_coordinate_count"], 0)
        self.assertEqual(result["quality"]["exact_duplicate_excess_rows"], 6)
        self.assertEqual(result["quality"]["zero_frp_count"], 17)
        self.assertEqual(result["coverage"]["indonesia_screening_bbox"]["rows"], 176)


if __name__ == "__main__":
    unittest.main()
