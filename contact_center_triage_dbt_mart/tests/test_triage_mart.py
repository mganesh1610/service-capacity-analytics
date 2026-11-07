import json
import sys
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from triage_sla_pipeline import run_triage_mart, two_prop_z


class TestContactCenterTriageMart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        val_path = MODULE_DIR / "results" / "triage_sla_validation.json"
        if val_path.exists():
            cls.summary = json.loads(val_path.read_text())
        else:
            cls.summary = run_triage_mart()

    def test_01_event_and_case_counts(self):
        self.assertEqual(self.summary["raw_event_snapshots"], 141712)
        self.assertEqual(self.summary["unique_cases"], 24918)
        self.assertEqual(self.summary["distinct_queues"], 71)
        self.assertEqual(
            self.summary["first_touch_triage_cases"] + self.summary["reassigned_multi_hop_cases"],
            24918,
        )

    def test_02_sla_and_cycle_time_metrics(self):
        self.assertAlmostEqual(self.summary["median_resolution_time_reduction_pct"], 50.01, places=2)
        sla = self.summary["sla_compliance_comparison"]
        self.assertAlmostEqual(sla["first_touch_rate_pct"], 78.39, places=2)
        self.assertAlmostEqual(sla["reassigned_rate_pct"], 45.58, places=2)
        self.assertAlmostEqual(sla["abs_diff_pp"], 32.81, places=2)
        self.assertGreater(sla["z_stat"], 50.0)

    def test_03_two_prop_z_boundary(self):
        res = two_prop_z(100, 200, 100, 200)
        self.assertEqual(res["abs_diff_pp"], 0.0)
        self.assertEqual(res["z_stat"], 0.0)


if __name__ == "__main__":
    unittest.main()
