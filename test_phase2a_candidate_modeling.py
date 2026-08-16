"""
Phase 2A Acceptance Test Suite — Candidate Modeling Verification

Tests all 15 Phase 2A acceptance criteria:
1. Baseline route uses actual current -> destination coordinates.
2. Reroute candidate does not use full baseline duration as delay.
3. Reroute exposes baseline duration and candidate duration separately.
4. Wait candidate exposes wait duration separately from total ETA.
5. Storage candidate does not use hardcoded 15 km placeholder.
6. Storage candidate calculates truck -> facility distance.
7. Storage candidate calculates facility -> destination distance.
8. Storage candidate calculates complete end-to-end duration.
9. Storage candidate does not hardcode shelf_life_ok=True.
10. Storage candidate evaluates final delivery deadline.
11. Threat Intelligence preserves authoritative disruption coordinates.
12. Threat Intelligence preserves source disruption information.
13. Only reroute, wait, and transfer_to_storage are valid actions.
14. transfer_to_another_vehicle is rejected.
15. All candidate options expose comparable explicit fields.
"""

import unittest
import json
import os

from agents.fleet_monitor import detect_disruption
from agents.threat_intel import ContractValidator
from agents.dispatch_gate import should_escalate
from agents.incident_planner import ContextBuilder, CandidateEvaluator, JSONValidator, VALID_RECOMMENDED_ACTIONS
from agents.risk_critic import DeterministicEvaluator, SAFE_ACTIONS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class TestPhase2ACandidateModeling(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DATA_DIR, "mock_fleet.json"), "r") as f:
            cls.fleet_data = json.load(f)
        with open(os.path.join(DATA_DIR, "mock_disruptions.json"), "r") as f:
            cls.disruptions_data = json.load(f)

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

    def test_01_baseline_route_uses_actual_coordinates(self):
        """1. Baseline route uses actual current -> destination coordinates."""
        self.assertIn("baseline_distance_km", self.context)
        self.assertIn("baseline_duration_hours", self.context)
        self.assertGreater(self.context["baseline_distance_km"], 500.0)
        self.assertGreater(self.context["baseline_duration_hours"], 5.0)

    def test_02_reroute_delay_not_equal_to_baseline_duration(self):
        """2. Reroute candidate does not use full baseline duration as delay."""
        reroute_cand = self.candidates_by_action.get("reroute")
        self.assertIsNotNone(reroute_cand)
        self.assertLess(reroute_cand.additional_delay_hours, reroute_cand.candidate_duration_hours)
        self.assertNotEqual(reroute_cand.additional_delay_hours, self.context["baseline_duration_hours"])

    def test_03_reroute_exposes_baseline_and_candidate_duration(self):
        """3. Reroute exposes baseline duration and candidate duration separately."""
        reroute_cand = self.candidates_by_action.get("reroute")
        self.assertIsNotNone(reroute_cand)
        self.assertGreater(reroute_cand.baseline_duration_hours, 0.0)
        self.assertGreater(reroute_cand.candidate_duration_hours, 0.0)
        self.assertEqual(
            reroute_cand.additional_delay_hours,
            round(max(0.0, reroute_cand.candidate_duration_hours - reroute_cand.baseline_duration_hours), 1)
        )

    def test_04_wait_exposes_wait_duration_separately_from_total_eta(self):
        """4. Wait candidate exposes wait duration separately from total ETA."""
        wait_cand = self.candidates_by_action.get("wait")
        self.assertIsNotNone(wait_cand)
        self.assertEqual(wait_cand.additional_delay_hours, 4.0)
        self.assertEqual(
            wait_cand.candidate_duration_hours,
            round(wait_cand.baseline_duration_hours + 4.0, 1)
        )

    def test_05_storage_does_not_use_hardcoded_15km(self):
        """5. Storage candidate does not use hardcoded 15 km placeholder."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertNotEqual(storage_cand.distance_km, 15.0)
        self.assertGreater(storage_cand.candidate_distance_km, 100.0)

    def test_06_storage_calculates_truck_to_facility_distance(self):
        """6. Storage candidate calculates truck -> facility distance."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertGreater(storage_cand.candidate_distance_km, 0.0)

    def test_07_storage_calculates_facility_to_destination_distance(self):
        """7. Storage candidate calculates facility -> destination distance."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertGreater(storage_cand.candidate_distance_km, self.context["baseline_distance_km"] - 100.0)

    def test_08_storage_calculates_complete_end_to_end_duration(self):
        """8. Storage candidate calculates complete end-to-end duration."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertGreater(storage_cand.candidate_duration_hours, self.context["baseline_duration_hours"])

    def test_09_storage_does_not_hardcode_shelf_life_ok_true(self):
        """9. Storage candidate does not hardcode shelf_life_ok=True."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        self.assertIsNotNone(storage_cand.shelf_life_margin_hours)
        expected_ok = (storage_cand.shelf_life_margin_hours >= 0.0)
        self.assertEqual(storage_cand.shelf_life_ok, expected_ok)

    def test_10_storage_evaluates_final_delivery_deadline(self):
        """10. Storage candidate evaluates final delivery deadline."""
        storage_cand = self.candidates_by_action.get("transfer_to_storage")
        self.assertIsNotNone(storage_cand)
        expected_deadline_ok = (storage_cand.deadline_margin_hours >= 0.0)
        self.assertEqual(storage_cand.deadline_ok, expected_deadline_ok)

    def test_11_threat_intel_preserves_authoritative_disruption_coordinates(self):
        """11. Threat Intelligence preserves authoritative disruption coordinates."""
        self.assertIn("authoritative_disruption", self.contract_2)
        auth_loc = self.contract_2["authoritative_disruption"]["location"]
        self.assertIsNotNone(auth_loc)
        self.assertEqual(auth_loc.get("lat"), 26.912)
        self.assertEqual(auth_loc.get("lng"), 75.787)

    def test_12_threat_intel_preserves_source_disruption_info(self):
        """12. Threat Intelligence preserves source disruption information."""
        self.assertIn("source_disruption_type", self.contract_2)
        self.assertIn("source_severity", self.contract_2)
        self.assertIn("source_predicted_delay", self.contract_2)
        self.assertEqual(self.contract_2["source_disruption_type"], "landslide")
        self.assertEqual(self.contract_2["source_severity"], "high")

    def test_13_only_3_actions_valid(self):
        """13. Only reroute, wait, transfer_to_storage, and no_feasible_action are valid actions."""
        self.assertEqual(VALID_RECOMMENDED_ACTIONS, {"reroute", "wait", "transfer_to_storage", "no_feasible_action"})
        self.assertEqual(SAFE_ACTIONS, {"reroute", "wait", "transfer_to_storage"})

    def test_14_transfer_to_another_vehicle_rejected(self):
        """14. transfer_to_another_vehicle is rejected."""
        invalid_payload = {
            "truck_id": "TRK-107",
            "recommended_action": "transfer_to_another_vehicle",
            "reasoning": "Attempting cross-docking onto another vehicle",
            "estimated_delay_hours": 2.0,
            "estimated_cost": 2000.0,
        }
        is_valid, _ = JSONValidator.validate_and_clean(invalid_payload, self.context)
        self.assertFalse(is_valid)
        self.assertNotIn("transfer_to_another_vehicle", [c.action for c in self.candidates])

    def test_15_candidates_expose_comparable_fields(self):
        """15. All candidate options expose comparable explicit fields."""
        for c in self.candidates:
            self.assertIsNotNone(c.action)
            self.assertIsNotNone(c.baseline_duration_hours)
            self.assertIsNotNone(c.candidate_duration_hours)
            self.assertIsNotNone(c.additional_delay_hours)
            self.assertIsNotNone(c.candidate_distance_km)
            self.assertIsNotNone(c.estimated_cost)
            self.assertIsNotNone(c.deadline_margin_hours)
            self.assertIsNotNone(c.shelf_life_margin_hours)
            self.assertIsNotNone(c.feasible)


if __name__ == "__main__":
    unittest.main()
