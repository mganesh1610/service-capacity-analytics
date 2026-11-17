import json
import unittest
from pathlib import Path

from contract_milestone_jira_sla_ops.jira_contract_sla_pipeline import (
    map_jira_priority_tier,
    two_prop_z,
    welch_t,
)


class TestJiraContractSLA(unittest.TestCase):
    def test_priority_mapping(self) -> None:
        self.assertEqual(map_jira_priority_tier("1 - Critical"), "P1_Critical")
        self.assertEqual(map_jira_priority_tier("2 - High"), "P2_High")
        self.assertEqual(map_jira_priority_tier("3 - Moderate"), "P3_Moderate")
        self.assertEqual(map_jira_priority_tier("4 - Low"), "P4_Low_Planning")

    def test_two_prop_z_detects_sla_lift(self) -> None:
        out = two_prop_z(780, 1000, 460, 1000)
        self.assertAlmostEqual(out["diff_pp"], 32.0, places=4)
        self.assertGreater(out["z_stat"], 14.0)

    def test_welch_t_detects_cycle_time_penalty(self) -> None:
        out = welch_t([120.0, 135.0, 128.0, 142.0], [24.0, 28.0, 22.0, 26.0])
        self.assertGreater(out["diff_hours"], 95.0)
        self.assertGreater(out["t_stat"], 20.0)

    def test_validation_summary_passes_all_gates(self) -> None:
        summary_file = Path(__file__).resolve().parent.parent / "results" / "validation_summary.json"
        if summary_file.exists():
            data = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(data["qa_gates_passed"], 10)
            self.assertEqual(data["canonical_jira_tickets"], 24918)
            self.assertEqual(data["source_events"], 141712)


if __name__ == "__main__":
    unittest.main()
