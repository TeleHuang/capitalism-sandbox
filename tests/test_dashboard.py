"""V0.5/V0.6 驾驶舱 API 裁剪测试（人口分组 + 行业机制元数据）。"""

from __future__ import annotations

import shutil
import subprocess
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


class SectorMetadataTests(unittest.TestCase):
    def test_sector_recipes_and_equipment_tiers(self):
        sectors = dashboard._sector_metadata()
        self.assertEqual(len(sectors), len(dashboard.SECTOR_PARAMS))
        by_id = {sector["id"]: sector for sector in sectors}

        steel = by_id["steel_mill"]
        inputs = {item["good"]: item["per_unit"] for item in steel["inputs"]}
        self.assertEqual(inputs, {"iron_ore": 1.5, "coal": 1.0})
        self.assertEqual(len(steel["equipment_tiers"]), 8)
        capacities = [tier["capacity"] for tier in steel["equipment_tiers"]]
        for previous, current in zip(capacities, capacities[1:]):
            self.assertAlmostEqual(current, previous * 2)
        self.assertEqual(steel["capital_goods"][0]["good"], "brick")
        self.assertEqual(steel["output_unit"], "吨")

        farm = by_id["agriculture"]
        self.assertTrue(farm["uses_land"])
        self.assertEqual(farm["fertilizer"]["per_mu"], dashboard.FERTILIZER_PER_MU)
        self.assertEqual(
            [tier["power"] for tier in farm["equipment_tiers"][:3]], [1.0, 2.0, 4.0]
        )
        # 农机功率翻倍但产能字段为 0：农业产出由土地决定，不由设备 capacity 决定。
        self.assertEqual(farm["equipment_tiers"][0]["capacity"], 0.0)

        coal = by_id["coal_mine"]
        self.assertTrue(coal["equipment_tiers"][0]["label"].startswith("徒手采矿"))
        self.assertTrue(coal["equipment_tiers"][1]["label"].startswith("矿井设备"))
        self.assertIn("没有“矿井”这个生产资料", coal["note"])

        service = by_id["service"]
        self.assertEqual(len(service["equipment_tiers"]), 1)
        self.assertFalse(service["capital_goods"])

    def test_run_meta_includes_units_sectors_and_mechanism(self):
        stats = [{"prices": {"food": 100.0, "machinery": 200.0}}]
        payload = dashboard._extract_payload(
            "classical", 1, 1, stats, [{}], 0.0, 0.0
        )
        meta = payload["meta"]
        self.assertEqual(meta["version"], "0.6.0")
        self.assertEqual(len(meta["sectors"]), len(dashboard.SECTOR_PARAMS))
        self.assertEqual(meta["mechanism"]["equipment_tiers"], 8)
        self.assertEqual(
            meta["mechanism"]["hunger"]["death_after_months"],
            dashboard.HUNGER_DEATH_AFTER_MONTHS,
        )
        goods = {good["id"]: good for good in meta["goods"]}
        self.assertEqual(goods["food"]["unit"], "吨")
        self.assertEqual(goods["machinery"]["unit"], "台")

    def test_capacity_and_equipment_units_come_from_supplements(self):
        stats = [
            {
                "firms": {"steel_mill": 1},
                "workers_by_industry": {"steel_mill": 3},
                "active_projects": {"steel_mill": 1},
            }
        ]
        supplements = [
            {
                "capacity_by_industry": {"steel_mill": 400.5},
                "equipment_units_by_industry": {"steel_mill": 2},
            }
        ]
        payload = dashboard._extract_payload(
            "classical", 1, 1, stats, supplements, 0.0, 0.0
        )
        industries = payload["industries"]
        self.assertEqual(industries["capacity"]["steel_mill"], [400.5])
        self.assertEqual(industries["equipment_units"]["steel_mill"], [2])

    def test_unknown_industry_uses_safe_fallback(self):
        sector = dashboard._fallback_sector("ranch", "meat")
        self.assertTrue(sector["unknown"])
        self.assertEqual(sector["output"], "meat")
        self.assertEqual(sector["output_unit"], "单位")
        self.assertEqual(sector["equipment_tiers"], [])
        self.assertEqual(dashboard._good_unit("meat"), "单位")

    def test_static_meta_lists_known_goods_with_units(self):
        meta = dashboard._static_meta()
        goods = {good["id"]: good for good in meta["goods"]}
        self.assertIn("food", goods)
        self.assertIn("service", goods)
        self.assertEqual(goods["brick"]["unit"], "块")
        self.assertEqual(len(meta["sectors"]), len(dashboard.SECTOR_PARAMS))


class FrontendSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_app_js_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(ROOT / "web" / "v04" / "app.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
