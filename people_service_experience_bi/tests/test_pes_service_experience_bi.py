#!/usr/bin/env python3
"""Unit tests for the P1 PES Service Delivery & Employee Experience BI Module."""

import unittest
from people_service_experience_bi.run_pes_service_experience_bi import (
    EXPECTED_ZIP_SHA256,
    RESULTS_DIR,
    run_pes_service_experience_bi,
)


class TestPESServiceExperienceBI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_pes_service_experience_bi()

    def test_01_provenance_and_consolidation_scale(self):
        self.assertEqual(self.summary["zip_sha256"], EXPECTED_ZIP_SHA256)
        self.assertEqual(self.summary["raw_event_snapshots"], 141712)
        self.assertEqual(self.summary["unique_service_cases"], 24918)
        self.assertAlmostEqual(
            self.summary["consolidation_row_reduction_pct"], 82.42, places=2
        )
        self.assertEqual(self.summary["assignment_groups_evaluated"], 71)

    def test_02_sla_and_solution_adoption_metrics(self):
        self.assertGreater(self.summary["kb_solution_adopted_cases"], 3000)
        self.assertAlmostEqual(
            self.summary["first_touch_vs_reassigned_sla"]["group_1_rate_pct"],
            78.39,
            places=2,
        )
        self.assertAlmostEqual(
            self.summary["first_touch_vs_reassigned_sla"]["group_2_rate_pct"],
            45.58,
            places=2,
        )

    def test_03_governance_and_escalation_gates(self):
        self.assertEqual(self.summary["quality_and_privacy_checks_passed"], 12)
        self.assertEqual(self.summary["quality_and_privacy_checks_total"], 12)
        self.assertGreater(self.summary["groups_escalated_to_pes_owners"], 0)
        self.assertGreater(self.summary["groups_suppressed_k_anonymity"], 0)
        self.assertTrue((RESULTS_DIR / "pes_service_experience_scorecard.csv").exists())


if __name__ == "__main__":
    unittest.main()
