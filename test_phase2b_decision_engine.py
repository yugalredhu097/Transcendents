"""
Phase 2B Acceptance Test Suite — Decision Engine Correction Verification

Tests all 17 Phase 2B acceptance criteria:
1. baseline duration > deadline for TRK-107.
2. baseline duration < shelf life for TRK-107.
3. wait total duration includes baseline journey (16.2h).
4. wait shelf life uses total journey (margin -2.2h).
5. reroute additional delay differs from total duration (0.4h vs 14.1h).
6. reroute feasibility uses total duration (14.1h > 8.0h -> infeasible).
7. storage includes facility -> destination (17.4h total).
8. storage deadline uses total end-to-end duration (17.4h > 8.0h -> infeasible).
9. storage shelf life uses total end-to-end duration.
10. authoritative disruption location survives Threat Intelligence.
11. authoritative disruption severity survives AI reinterpretation.
12. transfer_to_another_vehicle is absent from action space.
13. infeasible candidates cannot be selected by deterministic fallback.
14. Gemini cannot select a deterministically infeasible candidate.
15. no-feasible-action state when all three allowed candidates are infeasible.
16. Risk Critic rejects an infeasible selected candidate / no_feasible_action.
17. TRK-107 end-to-end scenario produces internally consistent margins.
"""

import unittest
import json
import os

from agents.fleet_monitor import detect_disruption
from agents.threat_intel import ContractValidator
from agents.dispatch_gate import should_escalate
from agents.incident_planner import (
    ContextBuilder,
    CandidateEvaluator,
    JSONValidator,
    PlanningService,
    VALID_RECOMMENDED_ACTIONS,
)
from agents.risk_critic import DeterministicEvaluator, SAFE_ACTIONS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class TestPhase2BDecisionEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DATA_DIR, "mock_fleet.json"), "r") as f:
            cls.fleet_data = json.load(f)

        cls.trk107_truck = next(t for t in cls.fleet_data if t.get("truck_id") == "TRK-107")
        cls.contract_1 = detect_disruption(cls.trk107_truck)

        cls.mock_threat_payload = {
            "truck_id": "TRK-107",
            "disruption_type": "roadblock",
            "description": "Debris blockade reported on NH-48 near Jaipur",
            "source": "mock_traffic_feed",
            "confidence": 0.8,
            "verified": True,
            "disruption_stage": "current",
            "predicted_delay_hours": 2.5,
            "predicted_disruption_delay": 2.5,
            "severity": "medium",
            "location": None,
        }
        cls.contract_2 = ContractValidator.validate_and_format(cls.mock_threat_payload, "TRK-107")
        cls.contract_3 = should_escalate(cls.contract_1, cls.contract_2)
        cls.context = ContextBuilder.build_context(cls.contract_3)
        cls.candidates = CandidateEvaluator.evaluate_candidates(cls.context)
        cls.candidates_by_action = {c.action: c for c in cls.candidates}

    def test_01_baseline_duration_exceeds_deadline(self):
        """1. baseline duration > deadline for TRK-107."""
        self.assertGreater(self.context["baseline_duration_hours"], self.context["deadline_hours"])
        self.assertFalse(self.context["baseline_deadline_ok"])

    def test_02_baseline_duration_within_shelf_life(self):
        """2. baseline duration < shelf life for TRK-107."""
        self.assertLess(self.context["baseline_duration_hours"], self.context["shelf_life_hours"])
        self.assertTrue(self.context["baseline_shelf_life_ok"])

    def test_03_wait_total_duration_includes_baseline(self):
        """3. wait total duration includes baseline journey (16.2h)."""
        wait_cand = self.candidates_by_action.get("wait")
        self.assertIsNotNone(wait_cand)
        self.assertEqual(
            wait_cand.candidate_duration_hours,
            round(self.context["baseline_duration_hours"] + 4.0, 1)
        )

    def test_04_wait_shelf_life_uses_total_journey(self):
        """4. wait shelf life uses total journey (margin -2.2h)."""
        wait_cand = self.candidates_by_action.get("wait")
        self.assertIsNotNone(wait_cand)
        expected_margin = round(self.context["shelf_life_hours"] - wait_cand.candidate_duration_hours, 1)
        self.assertEqual(wait_cand.shelf_life_margin_hours, expected_margin)
        self.assertFalse(wait_cand.shelf_life_ok)
        self.assertFalse(wait_cand.feasible)

    def test_05_reroute_additional_delay_differs_from_total_duration(self):
        """5. reroute additional delay differs from total duration (0.4h vs 14.1h)."""
        reroute_cand = self.candidates_by_action.get("reroute")
        self.assertIsNotNone(reroute_cand)
        self.assertNotEqual(reroute_cand.additional_delay_hours, reroute_cand.candidate_duration_hours)
        self.assertLess(reroute_cand.additional_delay_hours, 2.0)

    def test_06_reroute_feasibility_uses_total_duration(self):
        """6. reroute feasibility uses total duration (14.1h > 8.0h -> infeasible)."""
        reroute_cand = self.candidates_by_action.get("reroute")
        self.assertIsNotNone(reroute_cand)
        self.assertFalse(reroute_cand.deadline_ok)
        self.assertFalse(reroute_cand.feasible)

    def test_07_storage_includes_facility_to_destination(self):
        """7. storage includes facility -> destination (17.4h total)."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertGreater(storage_cand.candidate_duration_hours, self.context["baseline_duration_hours"])

    def test_08_storage_deadline_uses_total_end_to_end_duration(self):
        """8. storage deadline uses total end-to-end duration (17.4h > 8.0h -> infeasible)."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertFalse(storage_cand.deadline_ok)
        self.assertFalse(storage_cand.feasible)

    def test_09_storage_shelf_life_uses_total_end_to_end_duration(self):
        """9. storage shelf life uses total end-to-end duration."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertIsNotNone(storage_cand.shelf_life_margin_hours)
        expected_margin = round(self.context["shelf_life_hours"] - storage_cand.candidate_duration_hours, 1)
        self.assertEqual(storage_cand.shelf_life_margin_hours, expected_margin)
        self.assertFalse(storage_cand.shelf_life_ok)

    def test_10_authoritative_disruption_location_survives(self):
        """10. authoritative disruption location survives Threat Intelligence."""
        self.assertIn("authoritative_disruption", self.contract_2)
        loc = self.contract_2["authoritative_disruption"]["location"]
        self.assertEqual(loc.get("lat"), 26.912)
        self.assertEqual(loc.get("lng"), 75.787)

    def test_11_authoritative_disruption_severity_survives(self):
        """11. authoritative disruption severity survives AI reinterpretation."""
        self.assertEqual(self.contract_2["authoritative_disruption"]["severity"], "high")
        self.assertEqual(self.contract_2["authoritative_disruption"]["type"], "landslide")

    def test_12_transfer_to_another_vehicle_absent(self):
        """12. transfer_to_another_vehicle is absent from action space."""
        self.assertNotIn("transfer_to_another_vehicle", VALID_RECOMMENDED_ACTIONS)
        self.assertNotIn("transfer_to_another_vehicle", SAFE_ACTIONS)

    def test_13_infeasible_candidates_cannot_be_selected_by_fallback(self):
        """13. infeasible candidates cannot be selected by deterministic fallback."""
        plan = PlanningService._create_deterministic_fallback_plan(self.context, self.candidates)
        self.assertEqual(plan["recommended_action"], "no_feasible_action")

    def test_14_gemini_cannot_select_infeasible_candidate(self):
        """14. Gemini cannot select a deterministically infeasible candidate."""
        llm_payload_attempt = {
            "truck_id": "TRK-107",
            "recommended_action": "wait",
            "reasoning": "Attempting to select wait even though it is infeasible",
            "estimated_delay_hours": 2.5,
            "estimated_cost": 1400.0,
        }
        is_valid, cleaned = JSONValidator.validate_and_clean(llm_payload_attempt, self.context)
        # Because no candidates are feasible for TRK-107, action MUST be converted/enforced to no_feasible_action
        self.assertTrue(is_valid)
        self.assertEqual(cleaned["recommended_action"], "no_feasible_action")

    def test_15_no_feasible_action_state_when_all_infeasible(self):
        """15. no-feasible-action state when all three allowed candidates are infeasible."""
        plan = PlanningService.generate_plan(self.contract_3)
        self.assertEqual(plan["recommended_action"], "no_feasible_action")
        self.assertIn("No feasible operational action exists", plan["reasoning"])

    def test_16_risk_critic_rejects_no_feasible_action(self):
        """16. Risk Critic rejects an infeasible selected candidate / no_feasible_action."""
        plan = PlanningService.generate_plan(self.contract_3)
        risk_res = DeterministicEvaluator.evaluate({
            **plan,
            "fleet_output": self.context["fleet_output"],
            "threat_output": self.context["threat_output"],
            "remaining_shelf_life_hours": self.context["shelf_life_hours"],
        })
        self.assertEqual(risk_res["decision"], "REJECT")
        self.assertIn("No feasible operational action", risk_res["reasoning"])
        self.assertFalse(risk_res["risk_factors"]["eta_ok"])
        self.assertFalse(risk_res["risk_factors"]["shelf_life_ok"])
        self.assertTrue(risk_res["risk_factors"]["safety_ok"])

    def test_17_trk107_internally_consistent_margins(self):
        """17. TRK-107 end-to-end scenario produces internally consistent margins."""
        wait_cand = self.candidates_by_action["wait"]
        reroute_cand = self.candidates_by_action["reroute"]
        storage_cand = self.candidates_by_action["transfer_to_storage"]

        self.assertLess(wait_cand.deadline_margin_hours, 0.0)
        self.assertLess(wait_cand.shelf_life_margin_hours, 0.0)

        self.assertLess(reroute_cand.deadline_margin_hours, 0.0)
        self.assertLess(reroute_cand.shelf_life_margin_hours, 0.0)

        self.assertLess(storage_cand.deadline_margin_hours, 0.0)
        self.assertLess(storage_cand.shelf_life_margin_hours, 0.0)


if __name__ == "__main__":
    unittest.main()
