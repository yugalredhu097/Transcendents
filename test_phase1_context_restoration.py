import json
import os
import unittest

from agents.fleet_monitor import detect_disruption
from agents.threat_intel import ContractValidator, assess_threat
from agents.dispatch_gate import should_escalate
from agents.incident_planner import CandidateEvaluator, ContextBuilder, generate_plan
from agents.risk_critic import DeterministicEvaluator, evaluate_risk
from app import run_pipeline


class TestPhase1ContextRestoration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load authoritative mock datasets
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        with open(os.path.join(data_dir, "mock_fleet.json"), "r") as f:
            cls.fleet_data = json.load(f)
        with open(os.path.join(data_dir, "mock_disruptions.json"), "r") as f:
            cls.disruptions_data = json.load(f)

        cls.trk107_raw_truck = next(t for t in cls.fleet_data if t.get("truck_id") == "TRK-107")
        cls.trk107_raw_disruption = cls.disruptions_data.get("TRK-107", {})

    def test_part_a_fleet_monitor_contract_1(self):
        contract_1 = detect_disruption(self.trk107_raw_truck)

        # 1. truck_id
        self.assertEqual(contract_1.get("truck_id"), "TRK-107")
        # 2. shipment_id
        self.assertEqual(contract_1.get("shipment_id"), "SHP-107")
        # 3. cargo_type
        self.assertEqual(contract_1.get("cargo_type"), "perishable_produce")
        # 4. quantity
        self.assertEqual(contract_1.get("quantity"), 1200)
        # 5. unit
        self.assertEqual(contract_1.get("unit"), "crates")
        # 6. cargo_value
        self.assertEqual(contract_1.get("cargo_value"), 450000)
        # 7. priority
        self.assertEqual(contract_1.get("priority"), "HIGH")
        # 8. remaining_shelf_life_hours
        self.assertEqual(contract_1.get("remaining_shelf_life_hours"), 14.0)
        # 9. current location
        loc = contract_1.get("location")
        self.assertEqual((loc.get("lat"), loc.get("lng")), (27.18, 75.95))
        # 10. destination location
        dest_loc = contract_1.get("destination_location")
        self.assertEqual((dest_loc.get("lat"), dest_loc.get("lng")), (19.076, 72.8777))

    def test_part_b_threat_intel_contract_2(self):
        contract_2 = ContractValidator.validate_and_format(self.trk107_raw_disruption, "TRK-107")

        # 11. disruption location
        dis_loc = contract_2.get("location") or contract_2.get("disruption_location")
        self.assertIsNotNone(dis_loc)
        self.assertEqual((dis_loc.get("lat"), dis_loc.get("lng")), (26.912, 75.787))
        # 12. predicted disruption delay
        delay = contract_2.get("predicted_disruption_delay") or contract_2.get("predicted_delay_hours")
        self.assertEqual(delay, 4.0)

    def test_part_c_d_e_f_incident_planner_context(self):
        contract_1 = detect_disruption(self.trk107_raw_truck)
        contract_2 = ContractValidator.validate_and_format(self.trk107_raw_disruption, "TRK-107")
        contract_3 = should_escalate(contract_1, contract_2)

        ip_context = ContextBuilder.build_context(contract_3)

        # 13. deadline_hours_remaining == approx 8.0 hours
        self.assertAlmostEqual(ip_context.get("deadline_hours"), 8.0, delta=0.1)

        # 14 & 15. Incident Planner must NOT use fake Mumbai/Pune coordinates
        self.assertNotEqual(ip_context.get("start_coords"), (72.8777, 19.0760))
        self.assertNotEqual(ip_context.get("end_coords"), (73.8567, 18.5204))
        # Correct coordinates (lng, lat for OSRM)
        self.assertEqual(ip_context.get("start_coords"), (75.95, 27.18))
        self.assertEqual(ip_context.get("end_coords"), (72.8777, 19.076))

        # 16. shelf_life must NOT become None
        self.assertEqual(ip_context.get("shelf_life_hours"), 14.0)

        # 17. priority must NOT become "medium"
        self.assertEqual(ip_context.get("customer_priority"), "HIGH")

    def test_part_h_risk_critic_context(self):
        contract_1 = detect_disruption(self.trk107_raw_truck)
        contract_2 = ContractValidator.validate_and_format(self.trk107_raw_disruption, "TRK-107")

        plan_data = {
            "truck_id": "TRK-107",
            "recommended_action": "reroute",
            "estimated_delay_hours": 1.6,
            "estimated_cost": 850.0,
            "fleet_output": contract_1,
            "threat_output": contract_2,
            "remaining_shelf_life_hours": contract_1.get("remaining_shelf_life_hours"),
            "priority": contract_1.get("priority"),
            "cargo_value": contract_1.get("cargo_value"),
            "delivery_deadline": contract_1.get("delivery_deadline"),
            "disruption_location": contract_2.get("location"),
        }

        # 18. Risk Critic must receive shelf_life and not report unknown
        risk_output = DeterministicEvaluator.evaluate(plan_data)
        self.assertIsNotNone(risk_output)
        self.assertNotEqual(risk_output.get("shelf_life_status"), "unknown")
        self.assertEqual(risk_output.get("shelf_life_status"), "pass")

    def test_part_g_facility_no_arbitrary_fallback(self):
        # Build context where no facility matches required condition
        dummy_dispatch = {
            "truck_id": "TRK-DUMMY",
            "reason": "abnormal_stop",
            "fleet_output": {
                "cargo_type": "perishable_produce",
                "remaining_shelf_life_hours": 10.0,
                "deadline_hours_remaining": 4.0,
            },
            "threat_output": {},
            "use_osrm": False,
        }
        ip_context = ContextBuilder.build_context(dummy_dispatch)
        ip_context["facilities"] = []
        options = CandidateEvaluator.evaluate_candidates(ip_context)
        storage_opt = next((o for o in options if o.action == "transfer_to_storage"), None)
        self.assertIsNotNone(storage_opt)
        self.assertIn("No compatible storage facility available", storage_opt.description)


if __name__ == "__main__":
    unittest.main()
