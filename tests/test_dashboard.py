"""V0.5 驾驶舱 API 裁剪测试（人口分组）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import serve_dashboard as dashboard  # noqa: E402


class DemographyPayloadTests(unittest.TestCase):
    def _payload(self):
        stats = [
            {
                "population": 12,
                "children": 3,
                "working_age": 8,
                "retirees": 1,
                "labor_force": 8,
                "employed": 7,
                "births": 2,
                "deaths": 1,
                "birth_rate": 2 / 12,
                "death_rate": 1 / 12,
                "dependency_ratio": 4 / 8,
                "old_age_dependency": 1 / 8,
                "average_age": 33.5,
                "median_age": 31.0,
                "pension_contributions": 10.0,
                "pension_revenue": 12.0,
                "pension_spending": 5.0,
                "pension_balance": 7.0,
                "pension_fund": 20.0,
                "pension_recipients": 1,
                "age_histogram": {
                    "0-4": 2,
                    "5-9": 1,
                    "10-14": 0,
                },
            }
        ]
        return dashboard._extract_payload(
            "classical", 1, 1, stats, [{}], 0.0, 0.0
        )

    def test_demography_scalars_and_histogram_are_exposed(self):
        payload = self._payload()
        scalars = payload["scalars"]
        self.assertEqual(scalars["population"], [12])
        self.assertEqual(scalars["births"], [2])
        self.assertEqual(scalars["pension_revenue"], [12.0])
        self.assertAlmostEqual(scalars["dependency_ratio"][0], 0.5)
        demography = payload["demography"]
        self.assertIn("0-4", demography["age_buckets"])
        self.assertEqual(demography["age_histogram"]["0-4"], [2])
        self.assertEqual(demography["age_histogram"]["5-9"], [1])
        self.assertEqual(
            sum(
                demography["age_histogram"][bucket][0]
                for bucket in demography["age_buckets"]
            ),
            3,
        )

    def test_missing_demography_fields_default_to_zero(self):
        payload = dashboard._extract_payload(
            "classical", 1, 1, [{}], [{}], 0.0, 0.0
        )
        self.assertEqual(payload["scalars"]["population"], [0])
        self.assertEqual(payload["scalars"]["pension_fund"], [0.0])
        self.assertEqual(
            sum(
                payload["demography"]["age_histogram"][bucket][0]
                for bucket in payload["demography"]["age_buckets"]
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
