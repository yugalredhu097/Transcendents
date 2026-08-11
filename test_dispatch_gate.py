"""
Comprehensive Test Suite for Dispatch Gate Integration Point (Agent 3 - Escalation Gate)
"""
import json
import unittest
from agents.dispatch_gate import should_escalate, _eval_fleet_trigger, _eval_threat_trigger, _determine_reason


class TestDispatchGate(unittest.TestCase):

    def test_case1_no_escalation(self):
        """Test Case 1: Normal fleet status & no verified threat (No Escalation)."""
        fleet1 = {
            "truck_id": "TRK-104",
            "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
            "cargo_type": "perishable_produce",
            "destination": "Pune",
            "deadline": "2026-08-10T18:00:00",
            "status": "normal",
            "delay_minutes": 0,
            "last_updated": "2026-08-08T14:22:00"
        }
        threat1 = {
            "truck_id": "TRK-104",
            "disruption_type": "none",
            "description": "No active disruptions detected",
            "source": "mock",
            "confidence": 1.0,
            "verified": False,
            "disruption_stage": "none",
            "predicted_delay_hours": 0.0
        }

        out1 = should_escalate(fleet1, threat1)
        self.assertEqual(out1["truck_id"], "TRK-104")
        self.assertFalse(out1["escalate"])
        self.assertEqual(out1["reason"], "no_disruption")
        self.assertEqual(out1["fleet_output"], fleet1)
        self.assertEqual(out1["threat_output"], threat1)

    def test_case2_fleet_triggered_escalation(self):
        """Test Case 2: Fleet-triggered escalation (abnormal_stop)."""
        fleet2 = {
            "truck_id": "TRK-105",
            "location": {"lat": 26.912, "lng": 75.787, "name": "near Jaipur, RJ"},
            "cargo_type": "electronics",
            "destination": "Delhi",
            "deadline": "2026-08-11T12:00:00",
            "status": "abnormal_stop",
            "delay_minutes": 45,
            "last_updated": "2026-08-10T16:00:00"
        }
        threat2 = {
            "truck_id": "TRK-105",
            "disruption_type": "none",
            "description": "No verified threat",
            "source": "mock",
            "confidence": 0.5,
            "verified": False,
            "disruption_stage": "none",
            "predicted_delay_hours": 0.0
        }

        out2 = should_escalate(fleet2, threat2)
        self.assertEqual(out2["truck_id"], "TRK-105")
        self.assertTrue(out2["escalate"])
        self.assertEqual(out2["reason"], "abnormal_stop")

    def test_case3_threat_triggered_escalation(self):
        """Test Case 3: Threat-triggered escalation (verified threat, upcoming stage)."""
        fleet3 = {
            "truck_id": "TRK-104",
            "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
            "cargo_type": "perishable_produce",
            "destination": "Pune",
            "deadline": "2026-08-10T18:00:00",
            "status": "normal",
            "delay_minutes": 0,
            "last_updated": "2026-08-08T14:22:00"
        }
        threat3 = {
            "truck_id": "TRK-104",
            "disruption_type": "protest",
            "description": "Protest announced on NH-8 corridor near Jaipur",
            "source": "mock_or_url",
            "confidence": 0.8,
            "verified": True,
            "disruption_stage": "upcoming",
            "predicted_delay_hours": 5.0
        }

        out3 = should_escalate(fleet3, threat3)
        self.assertEqual(out3["truck_id"], "TRK-104")
        self.assertTrue(out3["escalate"])
        self.assertEqual(out3["reason"], "threat_upcoming")

    def test_case4_combined_triggers(self):
        """Test Case 4: Both abnormal_stop and verified current threat."""
        fleet4 = {"truck_id": "TRK-999", "status": "abnormal_stop"}
        threat4 = {"truck_id": "TRK-999", "verified": True, "disruption_stage": "current"}

        out4 = should_escalate(fleet4, threat4)
        self.assertEqual(out4["truck_id"], "TRK-999")
        self.assertTrue(out4["escalate"])
        self.assertEqual(out4["reason"], "abnormal_stop_and_threat_current")

    def test_case5_malformed_and_empty_inputs(self):
        """Test Case 5: Defensive handling of empty or None inputs."""
        out5 = should_escalate({}, {})
        self.assertEqual(out5["truck_id"], "UNKNOWN")
        self.assertFalse(out5["escalate"])
        self.assertEqual(out5["reason"], "no_disruption")


def run_tests():
    print("--- Running Dispatch Gate Agent Tests ---")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDispatchGate)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Dispatch Gate tests failed!")
    print("All Dispatch Gate Agent tests passed successfully!\n")


if __name__ == "__main__":
    run_tests()

